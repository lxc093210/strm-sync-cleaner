FROM python:3.11-slim

WORKDIR /app

COPY . /app

# 安装 Flask，用于 Web UI
RUN pip install --no-cache-dir flask

# Web UI 默认端口
EXPOSE 8000

CMD ["python", "/app/main.py"]
