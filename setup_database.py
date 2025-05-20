#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility để thiết lập cơ sở dữ liệu cho dự án.
Script này giúp người mới dễ dàng thiết lập cơ sở dữ liệu và tạo cấu trúc bảng cần thiết.
"""

import os
import sys
import logging
import argparse
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from pathlib import Path
import time
import json
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("setup_database.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def load_env_vars():
    """
    Kiểm tra và tải các biến môi trường cần thiết.
    Nếu không có file .env, tạo từ file .env.example.
    """
    try:
        # Thêm đường dẫn hiện tại vào sys.path
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        # Cố gắng import từ config.py
        try:
            from config import settings
            logger.info("Đã tải cấu hình từ config.py")
            database_url = settings.DATABASE_URL
        except (ImportError, AttributeError):
            # Nếu không thể import từ config.py, tải từ biến môi trường
            logger.warning("Không thể tải cấu hình từ config.py, đang sử dụng biến môi trường.")
            database_url = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5444/iot_db")
        
        # Kiểm tra xem file .env có tồn tại không
        env_path = Path(os.path.dirname(os.path.abspath(__file__))) / '.env'
        if not env_path.exists():
            example_env_path = Path(os.path.dirname(os.path.abspath(__file__))) / '.env.example'
            if example_env_path.exists():
                logger.warning("File .env không tồn tại. Đang tạo từ .env.example...")
                with open(example_env_path, 'r') as src, open(env_path, 'w') as dst:
                    dst.write(src.read())
                logger.info("Đã tạo file .env từ .env.example. Vui lòng kiểm tra và cập nhật thông tin cấu hình.")
        
        return database_url
    except Exception as e:
        logger.error(f"Lỗi khi tải biến môi trường: {str(e)}")
        raise

def check_database_connection(database_url):
    """
    Kiểm tra kết nối đến cơ sở dữ liệu.
    
    Args:
        database_url: URL kết nối đến cơ sở dữ liệu
        
    Returns:
        bool: True nếu kết nối thành công, False nếu thất bại
    """
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Kết nối đến cơ sở dữ liệu thành công!")
        return True
    except OperationalError as e:
        if "database" in str(e) and "does not exist" in str(e):
            logger.error(f"Cơ sở dữ liệu không tồn tại: {str(e)}")
            logger.info("Bạn cần tạo cơ sở dữ liệu trước khi thiết lập.")
            
            # Lấy thông tin DB từ URL
            if "postgresql://" in database_url:
                parts = database_url.split("/")
                db_name = parts[-1].split("?")[0]
                connection_string = "/".join(parts[:-1]) + "/postgres"  # Kết nối đến postgres db để tạo db mới
                
                logger.info(f"Đang thử kết nối đến database postgres để tạo '{db_name}'...")
                try:
                    engine = create_engine(connection_string)
                    with engine.connect() as conn:
                        conn.execute(text(f"CREATE DATABASE {db_name}"))
                        conn.commit()
                    logger.info(f"Đã tạo cơ sở dữ liệu '{db_name}' thành công!")
                    return True
                except Exception as create_err:
                    logger.error(f"Không thể tự động tạo cơ sở dữ liệu: {str(create_err)}")
                    logger.info(f"Vui lòng tạo cơ sở dữ liệu '{db_name}' thủ công và chạy lại script này.")
        else:
            logger.error(f"Lỗi kết nối đến cơ sở dữ liệu: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Lỗi không xác định khi kết nối đến cơ sở dữ liệu: {str(e)}")
        return False

def setup_tables(database_url):
    """
    Thiết lập các bảng cần thiết trong cơ sở dữ liệu.
    
    Args:
        database_url: URL kết nối đến cơ sở dữ liệu
        
    Returns:
        bool: True nếu cấu hình thành công, False nếu thất bại
    """
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        # Import các model
        try:
            from models import Base
            logger.info("Đã tải các model từ models.py")
        except ImportError:
            logger.error("Không thể import models. Vui lòng kiểm tra file models.py")
            return False
        
        # Tạo engine
        engine = create_engine(database_url)
        
        # Tạo tất cả các bảng
        Base.metadata.create_all(bind=engine)
        
        # Kiểm tra xem các bảng đã được tạo chưa
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = inspector.get_table_names()
            
        # In ra các bảng đã tạo
        logger.info(f"Các bảng hiện có trong cơ sở dữ liệu: {', '.join(tables)}")
        
        # Kiểm tra các bảng quan trọng
        required_tables = ['users', 'devices', 'sensor_data', 'original_samples', 'compressed_data_optimized', 'feeds']
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            logger.warning(f"Các bảng sau chưa được tạo: {', '.join(missing_tables)}")
        else:
            logger.info("Tất cả các bảng cần thiết đã được tạo thành công!")
        
        return True
    except Exception as e:
        logger.error(f"Lỗi khi thiết lập các bảng: {str(e)}")
        return False

def create_sample_data(database_url):
    """
    Tạo dữ liệu mẫu cho người mới bắt đầu.
    
    Args:
        database_url: URL kết nối đến cơ sở dữ liệu
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    try:
        # Import các model
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        try:
            from sqlalchemy.orm import sessionmaker
            from models import User, Device
            import datetime
        except ImportError as e:
            logger.error(f"Không thể import các model cần thiết: {str(e)}")
            return False
        
        # Tạo engine và session
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Kiểm tra xem đã có dữ liệu chưa
        existing_users = session.query(User).count()
        existing_devices = session.query(Device).count()
        
        if existing_users > 0 and existing_devices > 0:
            logger.info("Dữ liệu mẫu đã tồn tại, bỏ qua bước tạo dữ liệu mẫu.")
            return True
        
        # Tạo user mẫu
        sample_user = User(
            username="admin",
            email="admin@example.com",
            hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # "password"
        )
        session.add(sample_user)
        session.commit()
        session.refresh(sample_user)
        
        # Tạo device mẫu
        sample_devices = [
            Device(device_id="device001", name="Temperature Sensor", description="Cảm biến nhiệt độ phòng khách"),
            Device(device_id="device002", name="Humidity Sensor", description="Cảm biến độ ẩm phòng tắm"),
            Device(device_id="device003", name="Light Sensor", description="Cảm biến ánh sáng sân vườn")
        ]
        
        for device in sample_devices:
            session.add(device)
        
        session.commit()
        
        logger.info("Đã tạo dữ liệu mẫu thành công!")
        
        return True
    except Exception as e:
        logger.error(f"Lỗi khi tạo dữ liệu mẫu: {str(e)}")
        return False
    finally:
        if 'session' in locals():
            session.close()

def run_migrations(migrations_dir=None):
    """
    Chạy các file migration SQL để cập nhật cấu trúc cơ sở dữ liệu.
    
    Args:
        migrations_dir: Thư mục chứa các file migration
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    try:
        # Nếu không chỉ định thư mục, sử dụng thư mục mặc định
        if migrations_dir is None:
            migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
        
        # Kiểm tra xem thư mục migrations có tồn tại không
        if not os.path.exists(migrations_dir):
            logger.info(f"Thư mục migrations không tồn tại: {migrations_dir}")
            logger.info("Đang tạo thư mục migrations...")
            os.makedirs(migrations_dir)
            
            # Tạo file README.md để hướng dẫn
            readme_path = os.path.join(migrations_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write("# Thư mục Migrations\n\n")
                f.write("Thư mục này chứa các file SQL migration để cập nhật cấu trúc cơ sở dữ liệu.\n")
                f.write("Mỗi file migration nên có định dạng: `XX-tên_migration.sql` với XX là số thứ tự.\n\n")
                f.write("Để chạy một migration cụ thể, sử dụng lệnh:\n")
                f.write("```\npython run_migrations.py --file /path/to/migration.sql\n```\n\n")
                f.write("Để chạy tất cả các migration, sử dụng lệnh:\n")
                f.write("```\npython run_migrations.py --all\n```\n")
            
            logger.info(f"Đã tạo thư mục migrations tại: {migrations_dir}")
            return True
        
        # Kiểm tra xem có file SQL nào trong thư mục không
        migration_files = [f for f in os.listdir(migrations_dir) if f.endswith('.sql')]
        
        if not migration_files:
            logger.info("Không tìm thấy file migration nào trong thư mục.")
            return True
            
        # Sắp xếp các file migration theo tên
        migration_files.sort()
        
        # Import hàm chạy migration
        try:
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            from run_migrations import run_all_migrations
            
            # Chạy tất cả các migration
            success_count = run_all_migrations()
            
            if success_count > 0:
                logger.info(f"Đã chạy thành công {success_count} migration!")
            
            return True
        except ImportError:
            logger.warning("Không thể import run_migrations.py. Bỏ qua việc chạy migrations.")
            return True
            
    except Exception as e:
        logger.error(f"Lỗi khi chạy migrations: {str(e)}")
        return False

def setup_database(database_url):
    """
    Thiết lập cơ sở dữ liệu và tạo các bảng cần thiết.
    
    Args:
        database_url: URL kết nối đến cơ sở dữ liệu
    """
    try:
        engine = create_engine(database_url)
        
        # Kiểm tra và xóa bảng device_config nếu tồn tại
        inspector = inspect(engine)
        if 'device_config' in inspector.get_table_names():
            logger.info("Đang xóa bảng device_config cũ...")
            with engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS device_config;"))
                conn.commit()
            logger.info("Đã xóa bảng device_config thành công")
        
        # Danh sách các bảng cần thiết
        required_tables = ['users', 'devices', 'sensor_data', 'original_samples', 'compressed_data_optimized', 'feeds']
        
        # Kiểm tra các bảng hiện có
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        # Kiểm tra xem có bảng nào không cần thiết không
        tables_to_drop = [table for table in existing_tables if table not in required_tables]
        if tables_to_drop:
            logger.warning(f"Phát hiện các bảng không cần thiết: {tables_to_drop}")
            logger.warning("Các bảng này sẽ bị xóa để đảm bảo tính nhất quán của database")
            
            # Xóa các bảng không cần thiết
            with engine.connect() as conn:
                for table in tables_to_drop:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                        logger.info(f"Đã xóa bảng {table}")
                    except Exception as e:
                        logger.error(f"Lỗi khi xóa bảng {table}: {str(e)}")
                conn.commit()
        
        # Kiểm tra xem có bảng nào cần thiết bị thiếu không
        missing_tables = [table for table in required_tables if table not in existing_tables]
        if missing_tables:
            logger.warning(f"Thiếu các bảng cần thiết: {missing_tables}")
            logger.warning("Các bảng này sẽ được tạo mới")
            
            # Tạo các bảng còn thiếu
            from models import Base
            Base.metadata.create_all(bind=engine)
            logger.info("Đã tạo các bảng còn thiếu thành công")
        
        # Kiểm tra lại sau khi thiết lập
        inspector = inspect(engine)
        final_tables = inspector.get_table_names()
        logger.info(f"Các bảng hiện có trong database: {final_tables}")
        
        # Kiểm tra xem tất cả các bảng cần thiết đã có chưa
        if all(table in final_tables for table in required_tables):
            logger.info("Tất cả các bảng cần thiết đã được thiết lập thành công!")
        else:
            logger.error("Vẫn còn thiếu một số bảng cần thiết!")
            missing = [table for table in required_tables if table not in final_tables]
            logger.error(f"Các bảng còn thiếu: {missing}")
            raise Exception("Thiết lập database không hoàn tất!")
            
        # Tạo/cập nhật bảng sensor_data và feeds
        with engine.connect() as conn:
            # Tạo bảng feeds
            conn.execute(text("""
                DROP TABLE IF EXISTS feeds CASCADE;
                CREATE TABLE feeds (
                    id SERIAL PRIMARY KEY,
                    feed_id VARCHAR(255) NOT NULL,
                    device_id VARCHAR(255) NOT NULL,
                    CONSTRAINT uix_device_feed UNIQUE (device_id, feed_id),
                    CONSTRAINT feeds_device_id_fkey FOREIGN KEY (device_id) 
                    REFERENCES devices(device_id) ON DELETE CASCADE
                );
                CREATE INDEX idx_feeds_device_id ON feeds(device_id);
                CREATE INDEX idx_feeds_feed_id ON feeds(feed_id);
            """))
            logger.info("Đã tạo bảng feeds")
            
            # Tạo bảng sensor_data
            conn.execute(text("""
                DROP TABLE IF EXISTS sensor_data CASCADE;
                CREATE TABLE sensor_data (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR(255) NOT NULL,
                    feed_id VARCHAR(255) NOT NULL,
                    value FLOAT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT sensor_data_device_id_fkey FOREIGN KEY (device_id) 
                        REFERENCES devices(device_id) ON DELETE CASCADE,
                    CONSTRAINT sensor_data_device_feed_fkey FOREIGN KEY (device_id, feed_id)
                        REFERENCES feeds(device_id, feed_id) ON DELETE CASCADE
                );
                CREATE INDEX idx_sensor_data_device_feed ON sensor_data(device_id, feed_id);
                CREATE INDEX idx_sensor_data_timestamp ON sensor_data(timestamp);
            """))
            logger.info("Đã tạo bảng sensor_data")
            
            # Commit các thay đổi
            conn.commit()
        
    except Exception as e:
        logger.error(f"Lỗi khi thiết lập cơ sở dữ liệu: {str(e)}")
        raise

def main():
    """
    Hàm chính để thiết lập cơ sở dữ liệu.
    """
    parser = argparse.ArgumentParser(description='Thiết lập cơ sở dữ liệu cho dự án')
    parser.add_argument('--sample-data', action='store_true', help='Tạo dữ liệu mẫu')
    parser.add_argument('--migrations', action='store_true', help='Chạy các file migration')
    args = parser.parse_args()
    
    try:
        # Hiển thị banner
        print("""
╔═══════════════════════════════════════════════════╗
║                                                   ║
║       THIẾT LẬP CƠ SỞ DỮ LIỆU CHO DỰ ÁN IoT      ║
║                                                   ║
╚═══════════════════════════════════════════════════╝
        """)
        
        # Kiểm tra và tải các biến môi trường
        logger.info("Bước 1: Kiểm tra cấu hình môi trường...")
        database_url = load_env_vars()
        
        # Kiểm tra kết nối đến cơ sở dữ liệu
        logger.info(f"Bước 2: Kiểm tra kết nối đến cơ sở dữ liệu...")
        if not check_database_connection(database_url):
            logger.error("Không thể kết nối đến cơ sở dữ liệu. Vui lòng kiểm tra cấu hình và thử lại.")
            return 1
        
        # Thiết lập các bảng
        logger.info("Bước 3: Thiết lập các bảng...")
        if not setup_tables(database_url):
            logger.error("Không thể thiết lập các bảng. Vui lòng kiểm tra lỗi và thử lại.")
            return 1
        
        # Tạo dữ liệu mẫu nếu có yêu cầu
        if args.sample_data:
            logger.info("Bước 4: Tạo dữ liệu mẫu...")
            if not create_sample_data(database_url):
                logger.error("Không thể tạo dữ liệu mẫu. Vui lòng kiểm tra lỗi và thử lại.")
                return 1
        
        # Chạy migrations nếu có yêu cầu
        if args.migrations:
            logger.info("Bước 5: Chạy các file migration...")
            if not run_migrations():
                logger.error("Không thể chạy các file migration. Vui lòng kiểm tra lỗi và thử lại.")
                return 1
        
        # Hoàn thành
        logger.info("Thiết lập cơ sở dữ liệu thành công!")
        print("""
╔═══════════════════════════════════════════════════╗
║                                                   ║
║       CƠ SỞ DỮ LIỆU ĐÃ ĐƯỢC THIẾT LẬP XONG       ║
║                                                   ║
║  Username: admin                                  ║
║  Password: password                               ║
║                                                   ║
╚═══════════════════════════════════════════════════╝

Để tạo dữ liệu mẫu:
python setup_database.py --sample-data

Để chạy các file migration:
python setup_database.py --migrations

Để thiết lập lại toàn bộ (bao gồm dữ liệu mẫu và migrations):
python setup_database.py --sample-data --migrations
        """)
        
        return 0
    except Exception as e:
        logger.error(f"Lỗi không xác định: {str(e)}")
        return 1

if __name__ == "__main__":
    database_url = load_env_vars()
    setup_database(database_url) 