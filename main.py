from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
import subprocess
import os
import zipfile
import shutil

app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def download_wheels(package_name):
    temp_dir = f"/tmp/{package_name}"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    subprocess.run(["pip", "download", package_name, "-d", temp_dir])

    wheel_files = [f for f in os.listdir(temp_dir) if f.endswith(".whl")]
    zip_path = f"/tmp/{package_name}_dependencies"

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in wheel_files:
            zipf.write(os.path.join(temp_dir, file), arcname=file)

    shutil.rmtree(temp_dir)
    return zip_path


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/download")
async def download_dependencies(package_name: str = Form(...)):
    zip_path = download_wheels(package_name)
    return FileResponse(
        zip_path,
        media_type="application/octet-stream",
        filename=os.path.basename(zip_path),
    )
