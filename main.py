from fastapi import FastAPI, Body, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import subprocess
from datetime import datetime
import os
import zipfile
import shutil
import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import NoCredentialsError
from pydantic import BaseModel
import logging


logger = logging.getLogger("uvicorn")


app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# S3 client setup
s3 = boto3.client("s3")


def download_wheels(package_list: str):
    temp_dir = f"/tmp/{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    with open(os.path.join(temp_dir, "requirements.txt"), "w") as f:
        f.write(package_list)

    subprocess.run(["pip", "download", "-r", "requirements.txt", "-d", temp_dir])

    wheel_files = [f for f in os.listdir(temp_dir) if f.endswith(".whl")]
    zip_path = f"{temp_dir}.zip"

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in wheel_files:
            zipf.write(os.path.join(temp_dir, file), arcname=file)

    shutil.rmtree(temp_dir)
    return zip_path


def download_node_modules(package_list: str):
    temp_dir = f"/tmp/{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    with open(os.path.join(temp_dir, "package.json"), "w") as f:
        f.write(package_list)

    # Run npm install
    try:
        subprocess.run(["npm", "install"], cwd=temp_dir, check=True)
    except subprocess.CalledProcessError:
        shutil.rmtree(temp_dir)
        return None

    # Zip node_modules directory
    node_modules_dir = os.path.join(temp_dir, 'node_modules')
    zip_path = f"{temp_dir}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(node_modules_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=temp_dir)
                zipf.write(file_path, arcname=arcname)

    shutil.rmtree(temp_dir)
    return zip_path


def upload_to_s3(file_path, bucket_name, dir_path, s3_file_name):
    try:
        s3.upload_file(file_path, bucket_name, f"{dir_path}/{s3_file_name}")
        return f"s3://{bucket_name}/{dir_path}/{s3_file_name}"
    except FileNotFoundError:
        return "The file was not found"
    except NoCredentialsError:
        return "Credentials not available"
    except S3UploadFailedError:
        return f"Failed to upload to S3 s3://{bucket_name}/{s3_file_name}"


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload_dependencies(
    package_list: str = Body(embed=True),
    bucket_name: str = Body(embed=True),
    package_type: str = Body(embed=True),
):
    if package_type == "python":
        dir_path = "pypi"
        zip_path = download_wheels(package_list)
    elif package_type == "node":
        dir_path = "node_modules"
        zip_path = download_node_modules(package_list)
    else:
        raise HTTPException(status_code=400, detail="Invalid package type")

    if zip_path is None:
        raise HTTPException(status_code=500, detail="Failed to download package")

    s3_url = upload_to_s3(
        zip_path, bucket_name, dir_path, os.path.basename(zip_path)
    )
    return JSONResponse(content={"s3_url": s3_url})
