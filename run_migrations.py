#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script để thực thi các file SQL migration
"""

import os
import sys
import logging
import argparse
from sqlalchemy import create_engine, text

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("migrations.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Lấy thông tin kết nối từ biến môi trường
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "compression")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")

# Tạo URL kết nối
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def run_migration(file_path):
    """
    Thực thi file SQL migration
    
    Args:
        file_path: Đường dẫn đến file SQL
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    try:
        # Kiểm tra file tồn tại
        if not os.path.exists(file_path):
            logger.error(f"File migration không tồn tại: {file_path}")
            return False
            
        # Đọc nội dung file SQL
        with open(file_path, 'r') as f:
            sql_script = f.read()
            
        # Kết nối đến database
        engine = create_engine(DATABASE_URL)
        
        # Thực thi script
        with engine.connect() as conn:
            conn.execute(text(sql_script))
            conn.commit()
            
        logger.info(f"Đã thực thi migration thành công: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi thực thi migration {file_path}: {str(e)}")
        return False

def run_all_migrations():
    """
    Thực thi tất cả các file SQL trong thư mục migrations
    
    Returns:
        int: Số lượng migration đã chạy thành công
    """
    # Thư mục chứa các file migration
    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
    
    # Kiểm tra thư mục tồn tại
    if not os.path.exists(migrations_dir):
        logger.error(f"Thư mục migrations không tồn tại: {migrations_dir}")
        return 0
        
    # Lấy danh sách các file .sql và sắp xếp theo tên
    migration_files = [f for f in os.listdir(migrations_dir) if f.endswith('.sql')]
    migration_files.sort()
    
    if not migration_files:
        logger.warning("Không tìm thấy file migration nào trong thư mục")
        return 0
        
    # Thực thi từng file
    success_count = 0
    for file_name in migration_files:
        file_path = os.path.join(migrations_dir, file_name)
        logger.info(f"Đang thực thi migration: {file_name}")
        
        if run_migration(file_path):
            success_count += 1
        else:
            logger.error(f"Migration thất bại: {file_name}. Dừng quá trình migration.")
            break
            
    logger.info(f"Đã thực thi {success_count}/{len(migration_files)} migration thành công")
    return success_count

def main():
    """
    Hàm chính để thực thi các migration
    """
    parser = argparse.ArgumentParser(description='Thực thi các file SQL migration')
    parser.add_argument('--file', type=str, help='Đường dẫn đến file SQL migration cụ thể')
    parser.add_argument('--all', action='store_true', help='Thực thi tất cả các file migration trong thư mục migrations')
    
    args = parser.parse_args()
    
    if args.file:
        # Thực thi migration cụ thể
        if run_migration(args.file):
            logger.info("Migration thành công!")
        else:
            logger.error("Migration thất bại!")
            sys.exit(1)
    elif args.all:
        # Thực thi tất cả các migration
        count = run_all_migrations()
        if count > 0:
            logger.info("Quá trình migration hoàn tất!")
        else:
            logger.warning("Không có migration nào được thực thi!")
    else:
        logger.error("Vui lòng chỉ định --file hoặc --all")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main() 