from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
import subprocess
import os
import zipfile
import shutil
import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import NoCredentialsError

app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# S3 client setup
s3 = boto3.client("s3")


def download_wheels(package_name):
    temp_dir = f"/tmp/{package_name}"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    subprocess.run(["pip", "download", package_name, "-d", temp_dir])

    wheel_files = [f for f in os.listdir(temp_dir) if f.endswith(".whl")]
    zip_path = f"/tmp/{package_name}.zip"

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for file in wheel_files:
            zipf.write(os.path.join(temp_dir, file), arcname=file)

    shutil.rmtree(temp_dir)
    return zip_path


def upload_to_s3(file_path, bucket_name, s3_file_name):
    try:
        s3.upload_file(file_path, bucket_name, s3_file_name)
        return f"s3://{bucket_name}/{s3_file_name}"
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
    package_name: str = Form(...),
):
    zip_path = download_wheels(package_name)
    s3_url = upload_to_s3(
        zip_path, "dockerhub-sync", os.path.basename(zip_path)[: -len(".zip")]
    )
    return JSONResponse(content={"s3_url": s3_url})
