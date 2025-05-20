#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module chứa các hàm và cấu hình liên quan đến cơ sở dữ liệu.
File này cung cấp các hàm để tạo kết nối đến cơ sở dữ liệu và quản lý phiên làm việc.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging
import os
from typing import Generator
from config import settings

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lấy thông tin kết nối từ biến môi trường hoặc cấu hình
DATABASE_URL = settings.DATABASE_URL
logger.info(f"Database URL: {DATABASE_URL}")

# Tạo engine với URL đã được xác nhận
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Kiểm tra kết nối trước khi sử dụng
    pool_recycle=300,    # Tái sử dụng connection sau 5 phút
)

# Tạo session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency để lấy database session
def get_db() -> Generator:
    """
    Tạo và trả về phiên làm việc (session) với cơ sở dữ liệu.
    Đảm bảo session được đóng sau khi sử dụng xong.
    
    Yields:
        Generator: SQLAlchemy session.
    """
    db = SessionLocal()
    try:
        logger.debug("Database session created")
        yield db
    finally:
        logger.debug("Database session closed")
        db.close()

# Hàm để kiểm tra kết nối với database
def check_database_connection() -> bool:
    """
    Kiểm tra kết nối với cơ sở dữ liệu.
    
    Returns:
        bool: True nếu kết nối thành công, False nếu thất bại.
    """
    try:
        with engine.connect() as connection:
            logger.info("Successfully connected to database")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        return False

# Hàm khởi tạo database
def init_db() -> None:
    """
    Khởi tạo cơ sở dữ liệu và tạo các bảng nếu chúng chưa tồn tại.
    """
    from models import Base
    try:
        # Tạo tất cả các bảng được định nghĩa
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created (if they didn't exist)")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise 