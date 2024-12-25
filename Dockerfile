FROM --platform=linux/amd64 python:3.13-bookworm

WORKDIR /app

# requirements.txtをコンテナにコピーし、依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# install node 22.5.1
RUN apt-get update && apt-get install -y curl && curl -sL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs

# アプリケーションコードをコンテナにコピー
COPY . .

# Uvicornでアプリケーションを起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]