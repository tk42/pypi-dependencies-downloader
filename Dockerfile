# ベースイメージとしてPython 3.9を使用
FROM python:3.9

# 作業ディレクトリを作成
WORKDIR /app

# requirements.txtをコンテナにコピーし、依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコンテナにコピー
COPY main.py .

# Uvicornでアプリケーションを起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]