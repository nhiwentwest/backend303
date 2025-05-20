"""
Migration để cập nhật mối quan hệ giữa các bảng devices, feeds và sensor_data
"""
from sqlalchemy import text
from database import get_db
import logging

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_migration():
    db = next(get_db())
    try:
        # Kiểm tra các bảng cần thiết đã tồn tại chưa
        check_tables = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name IN ('devices', 'feeds', 'sensor_data');
        """)
        
        result = db.execute(check_tables).fetchall()
        existing_tables = [row[0] for row in result]
        
        if len(existing_tables) < 3:
            missing_tables = [table for table in ['devices', 'feeds', 'sensor_data'] if table not in existing_tables]
            logger.error(f"Thiếu các bảng: {', '.join(missing_tables)}")
            return False
        
        # 1. Cập nhật bảng feeds để đảm bảo device_id tham chiếu đến devices.device_id
        logger.info("Cập nhật bảng feeds...")
        
        # Kiểm tra xem đã có khóa ngoại chưa
        has_fk_query = text("""
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE constraint_name = 'feeds_device_id_fkey'
        AND table_name = 'feeds';
        """)
        
        has_fk = db.execute(has_fk_query).scalar() > 0
        
        if not has_fk:
            # Xóa khóa ngoại nếu đã tồn tại (để tránh lỗi)
            try:
                db.execute(text("ALTER TABLE feeds DROP CONSTRAINT IF EXISTS feeds_device_id_fkey;"))
            except:
                pass
                
            # Thêm khóa ngoại mới
            try:
                db.execute(text("""
                ALTER TABLE feeds
                ADD CONSTRAINT feeds_device_id_fkey
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
                ON DELETE CASCADE;
                """))
                logger.info("Đã thêm khóa ngoại feeds.device_id → devices.device_id")
            except Exception as e:
                logger.error(f"Lỗi khi thêm khóa ngoại cho feeds.device_id: {str(e)}")
                
        # 2. Cập nhật bảng sensor_data để đảm bảo feed_id tham chiếu đến feeds.feed_id
        logger.info("Cập nhật bảng sensor_data...")
        
        # Kiểm tra xem đã có khóa ngoại cho feed_id chưa
        has_feed_fk_query = text("""
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE constraint_name = 'sensor_data_feed_id_fkey'
        AND table_name = 'sensor_data';
        """)
        
        has_feed_fk = db.execute(has_feed_fk_query).scalar() > 0
        
        if not has_feed_fk:
            # Xóa khóa ngoại nếu đã tồn tại (để tránh lỗi)
            try:
                db.execute(text("ALTER TABLE sensor_data DROP CONSTRAINT IF EXISTS sensor_data_feed_id_fkey;"))
            except:
                pass
                
            # Thêm khóa ngoại mới cho feed_id
            try:
                db.execute(text("""
                ALTER TABLE sensor_data
                ADD CONSTRAINT sensor_data_feed_id_fkey
                FOREIGN KEY (feed_id) REFERENCES feeds(feed_id)
                ON DELETE CASCADE;
                """))
                logger.info("Đã thêm khóa ngoại sensor_data.feed_id → feeds.feed_id")
            except Exception as e:
                logger.error(f"Lỗi khi thêm khóa ngoại cho sensor_data.feed_id: {str(e)}")
        
        # 3. Cập nhật bảng sensor_data để đảm bảo device_id tham chiếu đến devices.device_id
        # Kiểm tra xem đã có khóa ngoại cho device_id chưa
        has_device_fk_query = text("""
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE constraint_name = 'sensor_data_device_id_fkey'
        AND table_name = 'sensor_data';
        """)
        
        has_device_fk = db.execute(has_device_fk_query).scalar() > 0
        
        if not has_device_fk:
            # Xóa khóa ngoại nếu đã tồn tại (để tránh lỗi)
            try:
                db.execute(text("ALTER TABLE sensor_data DROP CONSTRAINT IF EXISTS sensor_data_device_id_fkey;"))
            except:
                pass
                
            # Thêm khóa ngoại mới cho device_id
            try:
                db.execute(text("""
                ALTER TABLE sensor_data
                ADD CONSTRAINT sensor_data_device_id_fkey
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
                ON DELETE CASCADE;
                """))
                logger.info("Đã thêm khóa ngoại sensor_data.device_id → devices.device_id")
            except Exception as e:
                logger.error(f"Lỗi khi thêm khóa ngoại cho sensor_data.device_id: {str(e)}")
        
        # 4. Tạo index để tối ưu hiệu suất
        try:
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_sensor_data_feed_id ON sensor_data(feed_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_sensor_data_device_id ON sensor_data(device_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp);"))
            logger.info("Đã tạo các index cần thiết")
        except Exception as e:
            logger.error(f"Lỗi khi tạo index: {str(e)}")
        
        # Commit các thay đổi
        db.commit()
        logger.info("Đã cập nhật thành công mối quan hệ giữa các bảng")
        
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi cập nhật mối quan hệ: {str(e)}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = run_migration()
    
    if success:
        print("Cập nhật mối quan hệ thành công!")
    else:
        print("Không thể cập nhật mối quan hệ") 