#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script để khởi tạo toàn bộ database từ đầu.
Script này sẽ:
1. Xóa tất cả các bảng cũ nếu tồn tại
2. Tạo lại các bảng với cấu trúc mới nhất
3. Thêm các ràng buộc và chỉ mục cần thiết
"""

import logging
import os
import sys
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Kết nối database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/iot_db")

def run_migration():
    """
    Thực hiện migration để khởi tạo database
    """
    try:
        # Kết nối đến database
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                # Xóa tất cả các bảng cũ nếu tồn tại
                conn.execute(text("""
                    DROP TABLE IF EXISTS sensor_data CASCADE;
                    DROP TABLE IF EXISTS devices CASCADE;
                    DROP TABLE IF EXISTS users CASCADE;
                    DROP TABLE IF EXISTS original_samples CASCADE;
                    DROP TABLE IF EXISTS compressed_data_optimized CASCADE;
                    DROP TABLE IF EXISTS feeds CASCADE;
                """))
                logger.info("Đã xóa các bảng cũ")
                
                # Tạo bảng users
                conn.execute(text("""
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(255) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        hashed_password VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                logger.info("Đã tạo bảng users")
                
                # Tạo bảng devices
                conn.execute(text("""
                    CREATE TABLE devices (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(255) UNIQUE NOT NULL,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                logger.info("Đã tạo bảng devices")
                
                # Tạo bảng sensor_data
                conn.execute(text("""
                    CREATE TABLE sensor_data (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(255) NOT NULL,
                        feed_id VARCHAR(255) NOT NULL,
                        value FLOAT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE,
                        UNIQUE (device_id, feed_id)
                    )
                """))
                logger.info("Đã tạo bảng sensor_data")
                
                # Tạo bảng original_samples
                conn.execute(text("""
                    CREATE TABLE original_samples (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(255) NOT NULL,
                        value NUMERIC(10,2) NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                    )
                """))
                logger.info("Đã tạo bảng original_samples")
                
                # Tạo bảng compressed_data_optimized
                conn.execute(text("""
                    CREATE TABLE compressed_data_optimized (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(255) NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        compression_metadata JSONB,
                        templates JSONB,
                        encoded_stream JSONB,
                        time_range TSRANGE,
                        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                    )
                """))
                logger.info("Đã tạo bảng compressed_data_optimized")
                
                # Tạo bảng feeds
                conn.execute(text("""
                    CREATE TABLE feeds (
                        id SERIAL PRIMARY KEY,
                        feed_id VARCHAR(255) UNIQUE NOT NULL,
                        device_id VARCHAR(255) NOT NULL,
                        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                    )
                """))
                logger.info("Đã tạo bảng feeds")
                
                # Commit transaction
                transaction.commit()
                logger.info("Migration hoàn tất thành công")
                return True
                
            except Exception as e:
                transaction.rollback()
                logger.error(f"Lỗi khi thực hiện migration: {str(e)}")
                return False
                
    except Exception as e:
        logger.error(f"Lỗi khi kết nối database: {str(e)}")
        return False

if __name__ == "__main__":
    run_migration() 