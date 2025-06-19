"""Utility functions to download Rust crates recursively without relying on the local `cargo` binary.

The user supplies a TOML fragment that represents the `[dependencies]` section
of a `Cargo.toml` file.  This module parses that fragment, resolves the version
requirements by talking directly to the crates.io HTTP API and finally
downloads the resolved `.crate` tarballs (which are gzip-compressed tar
archives).  All `.crate` files are zipped into a single archive which is
returned to the caller.

The resolution algorithm is *good enough* for most simple version
specifications:

* Exact versions – e.g. `serde = "1.0.197"`
* Wildcards – `serde = "1"` or `serde = "1.0"` → resolves to the latest
  compatible version that starts with that prefix.
* Caret (`^`) and tilde (`~`) requirements are interpreted as their prefix
  equivalents.  For example `^1.2.3` is treated as `1`, `~1.2.3` as `1.2`.

The implementation intentionally keeps the dependency-resolution logic small
so that we don't pull in a heavy semver solver.  If a requirement cannot be
interpreted by the simple rules above we fall back to *exact-match only*.

NOTE: The crates.io API is rate-limited.  We keep requests at a minimum and use
basic in-memory caching.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Set, Tuple

import requests

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

logger = logging.getLogger(__name__)

CRATES_INDEX_URL = "https://crates.io/api/v1/crates/{crate}"
CRATE_DOWNLOAD_URL = (
    "https://static.crates.io/crates/{crate}/{crate}-{version}.crate"
)

# --------------------------------------------------------------------------------------
# Parsing dependency text
# --------------------------------------------------------------------------------------

def parse_dependencies_fragment(fragment: str) -> Dict[str, str]:
    """Parse the TOML *fragment* that lists dependencies.

    The caller is expected to provide the text that would normally appear
    under the `[dependencies]` heading.  We prepend the heading so the TOML
    parser can handle it.
    """
    toml_src = "[dependencies]\n" + fragment
    data = tomllib.loads(toml_src)
    deps: Dict[str, str | dict] = data["dependencies"]

    # We only care about the *version requirement*.  When the dependency is a
    # table it is usually of the form:
    #   foo = { version = "1", features = ["bar"] }
    # We ignore optional extras for now.
    extracted: Dict[str, str] = {}
    for crate, spec in deps.items():
        if isinstance(spec, str):
            extracted[crate] = spec
        elif isinstance(spec, dict):
            if "version" in spec and isinstance(spec["version"], str):
                extracted[crate] = spec["version"]
            else:
                # No version specified – assume latest
                extracted[crate] = "*"
        else:
            # Unknown TOML type – fallback to latest
            extracted[crate] = "*"
    return extracted

# --------------------------------------------------------------------------------------
# Semver helpers (very lightweight heuristic)
# --------------------------------------------------------------------------------------

def _version_prefix(requirement: str) -> str | None:
    """Return a string prefix that all acceptable versions must start with.

    We interpret the following cases:
    • "*" → None (any version)
    • "1" → "1."
    • "1.2" → "1.2."
    • "^1.2.3" → "1."
    • "~1.2.3" → "1.2."
    Otherwise we assume the requirement is an exact version and return it
    verbatim.
    """
    requirement = requirement.strip()
    if requirement == "*":
        return None

    # caret / tilde handling – keep only the numeric prefix
    if requirement.startswith("^") or requirement.startswith("~"):
        requirement = requirement[1:]

    # If the requirement is exact (contains any comparison operator), we can't
    # interpret it – treat as exact.
    if any(c in requirement for c in "><="):
        return requirement  # pragma: no cover – uncommon spec

    # If the requirement is fully numeric (X or X.Y or X.Y.Z), treat as prefix
    if re.fullmatch(r"\d+(?:\.\d+){0,2}", requirement):
        return requirement + "." if not requirement.endswith(".") and "." not in requirement[-1] else requirement

    # fallback – exact
    return requirement

# --------------------------------------------------------------------------------------
# Crates.io API interaction
# --------------------------------------------------------------------------------------

_session = requests.Session()
_session.headers["User-Agent"] = "pypi-dependencies-downloader/1.0"

_versions_cache: Dict[str, List[Dict]] = {}


def _fetch_crate_versions(crate: str) -> List[Dict]:
    if crate in _versions_cache:
        return _versions_cache[crate]
    url = CRATES_INDEX_URL.format(crate=crate)
    logger.debug("Fetching crate metadata: %s", url)
    resp = _session.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    _versions_cache[crate] = data["versions"]
    return _versions_cache[crate]


def _latest_satisfying_version(crate: str, requirement: str) -> Tuple[str, List[Dict]]:
    """Return (version, dependencies_of_version) that satisfies *requirement*."""
    versions = _fetch_crate_versions(crate)

    # Filter out yanked versions
    versions = [v for v in versions if not v.get("yanked", False)]

    if requirement == "*":
        chosen = max(versions, key=lambda v: v["num"])
        return chosen["num"], chosen["dependencies"]

    prefix = _version_prefix(requirement)
    if prefix is None:  # any version
        chosen = max(versions, key=lambda v: v["num"])
        return chosen["num"], chosen["dependencies"]

    if prefix == requirement and "<" not in requirement and ">" not in requirement and "=" in requirement:
        # exact match (e.g., "=1.2.3" not handled) – fallback
        for v in versions:
            if v["num"] == requirement:
                return v["num"], v["dependencies"]
        raise ValueError(f"No version {requirement} found for {crate}")

    # prefix match
    candidates = [v for v in versions if v["num"].startswith(prefix)]
    if not candidates:
        raise ValueError(f"No version satisfies {requirement} for {crate}")
    chosen = max(candidates, key=lambda v: v["num"])
    return chosen["num"], chosen["dependencies"]

# --------------------------------------------------------------------------------------
# Recursive resolution and download
# --------------------------------------------------------------------------------------

def resolve_dependency_tree(initial: Dict[str, str]) -> Dict[str, str]:
    """Resolve all dependencies recursively.

    Returns a mapping of crate name → resolved *exact* version.
    """
    resolved: Dict[str, str] = {}
    to_process: List[Tuple[str, str]] = list(initial.items())

    while to_process:
        crate, req = to_process.pop()
        if crate in resolved:
            continue
        try:
            version, deps = _latest_satisfying_version(crate, req)
        except Exception as e:
            logger.error("Failed to resolve %s (%s): %s", crate, req, e)
            continue
        resolved[crate] = version

        # Queue sub-dependencies (normal & build, skip dev)
        for dep in deps:
            if dep.get("kind") == "dev":
                continue
            dep_name = dep["crate_id"]
            dep_req = dep["req"]
            if dep_name not in resolved:
                to_process.append((dep_name, dep_req))
    return resolved


def download_crates_zip(dep_versions: Dict[str, str]) -> str:
    """Download all crates and pack them into a single zip archive.

    Returns the path to the created zip file.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="crates_"))
    try:
        for crate, version in dep_versions.items():
            url = CRATE_DOWNLOAD_URL.format(crate=crate, version=version)
            logger.info("Downloading %s %s", crate, version)
            resp = _session.get(url, timeout=30)
            resp.raise_for_status()
            file_path = temp_dir / f"{crate}-{version}.crate"
            file_path.write_bytes(resp.content)

        zip_path = str(temp_dir) + ".zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in temp_dir.iterdir():
                zipf.write(file, arcname=file.name)
        return zip_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# --------------------------------------------------------------------------------------
# High-level entry point used by main.py
# --------------------------------------------------------------------------------------

def download_crates_from_fragment(fragment: str) -> str:
    deps = parse_dependencies_fragment(fragment)
    dep_versions = resolve_dependency_tree(deps)
    logger.info("Resolved %d crates", len(dep_versions))
    return download_crates_zip(dep_versions)
