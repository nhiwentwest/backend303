# Stage 1: Build dependencies
FROM python:3.9.19-alpine AS builder

WORKDIR /app

# Cài đặt các dependencies build (nếu có C/C++ hoặc requirements cần build)
RUN apk add --no-cache build-base

# Copy requirements và cài vào thư mục tạm
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel --no-cache-dir
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Stage 2: Runtime image
FROM python:3.9.19-alpine

WORKDIR /app

# Copy dependencies đã build từ stage 1
COPY --from=builder /install /usr/local

# Copy mã nguồn
COPY . .

# Thêm script entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Chạy entrypoint khi container start
ENTRYPOINT ["/entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --spider -q http://localhost:8000/docs || exit 1 