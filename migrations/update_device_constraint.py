#!/usr/bin/env python3
"""
Script để cập nhật ràng buộc khóa ngoại cho bảng devices
"""

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_foreign_key_constraint():
    # Load biến môi trường
    load_dotenv()
    
    # Cấu hình Database
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as connection:
        # Kiểm tra ràng buộc hiện tại
        result = connection.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE constraint_type = 'FOREIGN KEY' 
              AND table_name = 'devices' 
              AND constraint_name LIKE '%user_id%'
        """)).fetchall()
        
        constraint_names = [row[0] for row in result]
        
        if constraint_names:
            logger.info(f"Tìm thấy các ràng buộc khóa ngoại: {constraint_names}")
            
            # Xóa các ràng buộc hiện tại
            for constraint_name in constraint_names:
                connection.execute(text(f"""
                    ALTER TABLE devices DROP CONSTRAINT IF EXISTS {constraint_name}
                """))
                logger.info(f"Đã xóa ràng buộc: {constraint_name}")
        
        # Kiểm tra xem cột user_id có cho phép NULL không
        result = connection.execute(text("""
            SELECT is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'devices' AND column_name = 'user_id'
        """)).scalar()
        
        if result.lower() != 'yes':
            # Cập nhật cột user_id để cho phép NULL
            connection.execute(text("""
                ALTER TABLE devices ALTER COLUMN user_id DROP NOT NULL
            """))
            logger.info("Đã cập nhật cột user_id để cho phép NULL")
        
        # Thêm ràng buộc khóa ngoại mới
        connection.execute(text("""
            ALTER TABLE devices 
            ADD CONSTRAINT devices_user_id_fkey 
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        """))
        logger.info("Đã thêm ràng buộc khóa ngoại mới cho phép NULL")
        
        connection.commit()
        logger.info("Đã cập nhật ràng buộc khóa ngoại thành công")

if __name__ == "__main__":
    try:
        update_foreign_key_constraint()
        print("Đã cập nhật ràng buộc khóa ngoại thành công!")
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật ràng buộc khóa ngoại: {str(e)}")
        print(f"Lỗi: {str(e)}") 