# pypi-dependencies-downloader

A simple script to download all dependencies of a package from PyPI.

![](./image.png)

## Quick Start

```bash
docker-compose run app
```

Access ```http://localhost:8000/``` and input the package name and the bucket name of your S3 to upload the dependencies libraries.


## Change the target version
You can change the target version of the package in the ```Dockerfile```.

```Dockerfile
FROM --platform=linux/amd64 python:3.8
```

to your target environment and target version.