#!/bin/bash
set -e

# Chờ DB sẵn sàng
./wait-for-it.sh db:5432 --timeout=60 --strict -- echo "Database is up"

# Chạy migrate Alembic
alembic upgrade head

# Chạy ứng dụng FastAPI với nhiều worker
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 