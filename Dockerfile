FROM python:3.11-slim

WORKDIR /app

# 时区（可选）
ENV TZ=Asia/Shanghai

# 复制你的 main.py
COPY main.py /app/main.py

# 运行主脚本
CMD ["python", "-u", "main.py"]

