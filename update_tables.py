from sqlalchemy import create_engine, Column, String, MetaData, Table, text, inspect
from sqlalchemy.ext.declarative import declarative_base
import logging
import sys
from config import settings
import models

# Cấu hình logging chi tiết hơn
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('update_tables.log')
    ]
)
logger = logging.getLogger(__name__)

def check_column_exists(conn, table_name, column_name):
    """Kiểm tra xem cột có tồn tại trong bảng hay không"""
    try:
        # Sử dụng inspector để lấy thông tin cột
        insp = inspect(conn)
        columns = [col['name'] for col in insp.get_columns(table_name)]
        
        exists = column_name in columns
        logger.info(f"Kiểm tra cột {column_name} trong bảng {table_name}: {'Đã tồn tại' if exists else 'Chưa tồn tại'}")
        return exists
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra cột {column_name}: {str(e)}")
        return False

def add_column_with_raw_sql(conn, table_name, column_name, column_type="VARCHAR"):
    """Thêm cột mới sử dụng SQL thuần"""
    try:
        sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type};"
        logger.info(f"Đang thực thi SQL: {sql}")
        conn.execute(text(sql))
        conn.commit()
        logger.info(f"Đã thực thi SQL thành công")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi thêm cột với SQL thuần: {str(e)}")
        return False

def drop_column_with_raw_sql(conn, table_name, column_name):
    """Xóa cột sử dụng SQL thuần"""
    try:
        sql = f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name};"
        logger.info(f"Đang thực thi SQL: {sql}")
        conn.execute(text(sql))
        conn.commit()
        logger.info(f"Đã xóa cột {column_name} khỏi bảng {table_name} thành công")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi xóa cột {column_name}: {str(e)}")
        return False

def update_compressed_data_table(conn):
    """Cập nhật bảng compressed_data, loại bỏ các cột không cần thiết"""
    try:
        logger.info("Đang cập nhật bảng compressed_data...")
        
        # Kiểm tra các cột cần xóa
        columns_to_drop = ["original_data", "error", "processing_time", "compression_method"]
        for column in columns_to_drop:
            if check_column_exists(conn, "compressed_data", column):
                # Xóa cột
                drop_column_with_raw_sql(conn, "compressed_data", column)
        
        logger.info("Đã cập nhật bảng compressed_data thành công")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật bảng compressed_data: {str(e)}")
        return False

def update_tables():
    try:
        # Kết nối đến database
        logger.info(f"Đang kết nối đến database với URL: {settings.DATABASE_URL}")
        engine = create_engine(settings.DATABASE_URL)
        
        # Kiểm tra kết nối
        with engine.connect() as conn:
            logger.info("Đã kết nối thành công đến database")
            
            # Cập nhật bảng compressed_data
            update_compressed_data_table(conn)
            
            # Kiểm tra xem bảng sensor_data đã tồn tại chưa
            insp = inspect(conn)
            tables = insp.get_table_names()
            
            # Kiểm tra bảng sensor_data
            if 'sensor_data' in tables:
                logger.info("Bảng sensor_data đã tồn tại")
                # Kiểm tra xem cột raw_data đã tồn tại chưa
                has_raw_data = check_column_exists(conn, 'sensor_data', 'raw_data')
                
                if not has_raw_data:
                    logger.info("Đang thêm cột raw_data vào bảng sensor_data...")
                    
                    # Thử cách 1: Sử dụng SQLAlchemy
                    try:
                        logger.info("Phương pháp 1: Sử dụng SQLAlchemy execute")
                        conn.execute(text('ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS raw_data VARCHAR;'))
                        conn.commit()
                        logger.info("Phương pháp 1 thành công")
                    except Exception as e1:
                        logger.warning(f"Phương pháp 1 thất bại: {str(e1)}")
                        
                        # Thử cách 2: Sử dụng hàm trợ giúp với SQL thuần
                        try:
                            logger.info("Phương pháp 2: Sử dụng SQL thuần")
                            add_column_with_raw_sql(conn, 'sensor_data', 'raw_data')
                            logger.info("Phương pháp 2 thành công")
                        except Exception as e2:
                            logger.error(f"Phương pháp 2 thất bại: {str(e2)}")
                            
                            # Thử cách 3: Tạo lại bảng với cấu trúc mới
                            try:
                                logger.info("Phương pháp 3: Tạo lại model metadata")
                                # Tạo lại bảng theo model
                                models.Base.metadata.create_all(bind=engine)
                                logger.info("Phương pháp 3 thành công")
                            except Exception as e3:
                                logger.error(f"Phương pháp 3 thất bại: {str(e3)}")
                                return False
                    
                    # Kiểm tra lại sau khi thêm
                    has_raw_data_after = check_column_exists(conn, 'sensor_data', 'raw_data')
                    if has_raw_data_after:
                        logger.info("✅ Đã thêm thành công cột raw_data vào bảng sensor_data")
                    else:
                        logger.error("❌ Không thể thêm cột raw_data vào bảng sensor_data")
                        return False
                else:
                    logger.info("Cột raw_data đã tồn tại trong bảng sensor_data")
            else:
                logger.info("Bảng sensor_data chưa tồn tại, sẽ được tạo")
            
            # Kiểm tra bảng compressed_data
            if 'compressed_data' in tables:
                logger.info("Bảng compressed_data đã tồn tại")
                # Không cần thêm cột compression_method vì chúng ta đã loại bỏ nó
            else:
                logger.info("Bảng compressed_data chưa tồn tại, sẽ được tạo")
            
            # Tạo tất cả các bảng nếu chưa tồn tại
            logger.info("Tạo tất cả các bảng từ models...")
            models.Base.metadata.create_all(bind=engine)
            logger.info("Đã tạo các bảng từ models thành công")
                
            # Kiểm tra xem bảng và cột đã được tạo chưa
            with engine.connect() as new_conn:
                tables_after = inspect(new_conn).get_table_names()
                logger.info(f"Các bảng hiện có: {', '.join(tables_after)}")
                
                if 'compressed_data' in tables_after:
                    # Không cần kiểm tra cột compression_method nữa
                    pass
                
                if 'sensor_data' in tables_after:
                    has_raw_data = check_column_exists(new_conn, 'sensor_data', 'raw_data')
                    logger.info(f"Kiểm tra cột raw_data trong sensor_data: {'Đã tồn tại' if has_raw_data else 'Chưa tồn tại'}")
            
        logger.info("Cập nhật cấu trúc bảng thành công")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật cấu trúc bảng: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    logger.info("=== BẮT ĐẦU CẬP NHẬT CẤU TRÚC BẢNG ===")
    success = update_tables()
    logger.info(f"=== KẾT THÚC CẬP NHẬT CẤU TRÚC BẢNG: {'THÀNH CÔNG' if success else 'THẤT BẠI'} ===") 