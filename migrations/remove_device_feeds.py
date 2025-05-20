"""
Migration để xóa bảng device_feeds
"""
from sqlalchemy import text
from database import get_db

def run_migration():
    db = next(get_db())
    try:
        # Kiểm tra bảng device_feeds có tồn tại không
        check_table = text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'device_feeds'
        );
        """)
        
        exists = db.execute(check_table).scalar()
        
        if exists:
            # Xóa bảng nếu tồn tại
            drop_table = text("DROP TABLE IF EXISTS device_feeds;")
            db.execute(drop_table)
            db.commit()
            print("Đã xóa bảng device_feeds")
        else:
            print("Bảng device_feeds không tồn tại")
            
    except Exception as e:
        db.rollback()
        print(f"Lỗi khi xóa bảng device_feeds: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    run_migration() 