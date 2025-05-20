# Stage 1: Build dependencies
FROM python:3.9.19-slim AS builder

WORKDIR /app

# Cài đặt các dependencies build (nếu có C/C++ hoặc requirements cần build)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential

# Copy requirements và cài vào thư mục tạm
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Stage 2: Runtime image
FROM python:3.9.19-slim

WORKDIR /app

# Copy dependencies đã build từ stage 1
COPY --from=builder /install /usr/local

# Copy mã nguồn
COPY . .

# Chạy ứng dụng
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl --fail http://localhost:8000/docs || exit 1 