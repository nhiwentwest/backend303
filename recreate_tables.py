from sqlalchemy import create_engine, text
import models
import logging
import os

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recreate_tables():
    try:
        # Lấy thông tin kết nối từ biến môi trường
        DB_USER = os.getenv("DB_USER", "postgres")
        DB_PASS = os.getenv("DB_PASS", "postgres")
        DB_NAME = os.getenv("DB_NAME", "compression")
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5433")
        
        # Tạo URL kết nối
        DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        
        # Tạo engine để kết nối
        engine = create_engine(DATABASE_URL)
        
        # Xóa tất cả các bảng cũ
        logger.info("Dropping all tables...")
        models.Base.metadata.drop_all(bind=engine)
        logger.info("All tables dropped successfully")
        
        # Tạo lại các bảng mới
        logger.info("Creating new tables...")
        models.Base.metadata.create_all(bind=engine)
        logger.info("All tables created successfully")
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")

if __name__ == "__main__":
    recreate_tables() 