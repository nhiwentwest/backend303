#!/usr/bin/env python3
"""
Script để chạy migration
"""

import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_migration(migration_file):
    """Chạy migration từ file SQL"""
    # Load biến môi trường
    load_dotenv()
    
    # Cấu hình Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    
    try:
        # Đọc file SQL
        with open(migration_file, 'r') as file:
            sql_commands = file.read()
        
        # Thực thi các lệnh SQL
        with engine.connect() as connection:
            connection.execute(text(sql_commands))
            connection.commit()
        
        logger.info(f"Đã chạy migration thành công từ file: {migration_file}")
        
    except Exception as e:
        logger.error(f"Lỗi khi chạy migration: {str(e)}")
        raise

if __name__ == "__main__":
    # Chạy migration mới nhất
    migration_file = "init-db/04_create_feed_device_mapping.sql"
    run_migration(migration_file) 