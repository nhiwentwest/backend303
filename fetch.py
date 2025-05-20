#!/usr/bin/env python3
"""
Script để lấy dữ liệu từ Adafruit IO và lưu vào database PostgreSQL
"""

import os
import sys
import logging
import requests
import argparse
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text, UniqueConstraint, and_
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load biến môi trường
load_dotenv()

# Cấu hình Adafruit IO
ADAFRUIT_IO_USERNAME = os.getenv("ADAFRUIT_IO_USERNAME")
ADAFRUIT_IO_KEY = os.getenv("ADAFRUIT_IO_KEY")
BASE_URL = f"https://io.adafruit.com/api/v2/{ADAFRUIT_IO_USERNAME}"

# Cấu hình Database
DATABASE_URL = os.getenv("DATABASE_URL")
logger.info(f"Database URL: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)

# Kiểm tra kết nối
try:
    with engine.connect() as conn:
        logger.info("Kết nối database thành công")
except Exception as e:
    logger.error(f"Lỗi kết nối database: {str(e)}")
    sys.exit(1)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tạo model
Base = declarative_base()

class Feed(Base):
    __tablename__ = "feeds"
    
    id = Column(Integer, primary_key=True, index=True)
    feed_id = Column(String, unique=True, index=True)
    device_id = Column(String, index=True)

class SensorData(Base):
    __tablename__ = "sensor_data"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    feed_id = Column(String, index=True)
    value = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('device_id', 'feed_id', 'timestamp', name='uix_device_feed_time'),
    )

def get_feeds():
    """Lấy danh sách tất cả feeds từ Adafruit IO"""
    headers = {
        "X-AIO-Key": ADAFRUIT_IO_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/feeds", headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Lỗi khi lấy feeds: {str(e)}")
        return []

def get_feed_data(feed_key, limit=100, start_time=None):
    """Lấy dữ liệu từ một feed cụ thể"""
    headers = {
        "X-AIO-Key": ADAFRUIT_IO_KEY,
        "Content-Type": "application/json"
    }
    
    params = {"limit": limit}
    if start_time:
        # Đảm bảo format đúng định dạng ISO 8601 cho Adafruit IO
        iso_time = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        params["start_time"] = iso_time
        logger.info(f"Lấy dữ liệu từ {iso_time} (UTC) cho feed {feed_key} (limit={limit})")
    else:
        logger.info(f"Lấy {limit} điểm dữ liệu mới nhất cho feed {feed_key}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/feeds/{feed_key}/data",
            headers=headers,
            params=params
        )
        
        if response.status_code != 200:
            logger.error(f"Lỗi khi lấy dữ liệu feed {feed_key}: HTTP {response.status_code}")
            logger.error(f"Response: {response.text}")
            return []
            
        response.raise_for_status()
        data = response.json()
        logger.info(f"Đã nhận {len(data)} điểm dữ liệu từ feed {feed_key}")
        return data
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu feed {feed_key}: {str(e)}")
        return []

def ensure_device_exists(db, device_id):
    """Đảm bảo device_id tồn tại trong bảng devices"""
    try:
        # Kiểm tra xem device đã tồn tại chưa
        device = db.execute(text("SELECT 1 FROM devices WHERE device_id = :device_id"), 
                           {"device_id": device_id}).first()
        
        if device:
            logger.info(f"Device đã tồn tại: device_id={device_id}")
            return True
        
        # Nếu chưa tồn tại, tạo device mới
        db.execute(
            text("INSERT INTO devices (device_id, user_id) VALUES (:device_id, NULL)"),
            {"device_id": device_id}
        )
        db.commit()
        
        logger.info(f"Đã tạo device mới: device_id={device_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi tạo device: {str(e)}")
        return False

def ensure_feed_exists(db, feed_id, device_id=None):
    """
    Đảm bảo feed tồn tại trong bảng feeds và được liên kết với thiết bị đúng
    
    Args:
        db: Database session
        feed_id: ID của feed
        device_id: ID của thiết bị (nếu đã biết)
        
    Returns:
        str: device_id được liên kết với feed
    """
    try:
        # Kiểm tra xem feed đã tồn tại chưa
        feed = db.query(Feed).filter(Feed.feed_id == feed_id).first()
        
        if feed:
            logger.info(f"Feed đã tồn tại: feed_id={feed_id}, device_id={feed.device_id}")
            
            # Nếu device_id được cung cấp và khác với device_id đã lưu, cập nhật nó
            if device_id and feed.device_id != device_id:
                # Đảm bảo device mới tồn tại
                if ensure_device_exists(db, device_id):
                    old_device_id = feed.device_id
                    
                    # Cập nhật feed để sử dụng device_id mới
                    feed.device_id = device_id
                    db.commit()
                    
                    # Kiểm tra và cập nhật sensor_data tương ứng
                    try:
                        db.execute(
                            text("""
                                UPDATE sensor_data 
                                SET device_id = :new_device_id 
                                WHERE device_id = :old_device_id AND feed_id = :feed_id
                            """),
                            {
                                "new_device_id": device_id,
                                "old_device_id": old_device_id,
                                "feed_id": feed_id
                            }
                        )
                        db.commit()
                        logger.info(f"Đã cập nhật sensor_data cho feed_id={feed_id} từ device_id={old_device_id} sang device_id={device_id}")
                    except Exception as e:
                        logger.warning(f"Lỗi khi cập nhật sensor_data: {str(e)}")
                    
                    logger.info(f"Đã cập nhật feed_id={feed_id} từ device_id={old_device_id} sang device_id={device_id}")
            
            return feed.device_id
        
        # Nếu không có device_id được cung cấp, tạo từ feed_id
        if not device_id:
            device_id = f"device-{feed_id}"
        
        # Đảm bảo thiết bị tồn tại
        ensure_device_exists(db, device_id)
        
        # Tạo feed mới
        new_feed = Feed(feed_id=feed_id, device_id=device_id)
        db.add(new_feed)
        db.commit()
        
        logger.info(f"Đã tạo feed mới: feed_id={feed_id}, device_id={device_id}")
        return device_id
        
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi tạo feed: {str(e)}")
        raise

def save_to_database(feed_id, data_points):
    """Lưu dữ liệu vào database"""
    db = SessionLocal()
    count = 0
    
    try:
        # Lấy device_id từ feed
        device_id = ensure_feed_exists(db, feed_id)
        logger.info(f"Đang lưu dữ liệu cho device_id: {device_id}, feed_id: {feed_id}")
        
        for point in data_points:
            try:
                # Lấy giá trị từ point
                raw_value = point.get("value")
                logger.debug(f"Giá trị thô: {raw_value}")
                
                # Xử lý giá trị JSON
                if isinstance(raw_value, dict):
                    value = raw_value.get("value")
                    if value is None:
                        logger.warning(f"Bỏ qua giá trị JSON không có trường value: {raw_value}")
                        continue
                    raw_value = value
                
                # Chỉ lưu các giá trị số
                try:
                    value = float(raw_value)
                except (ValueError, TypeError):
                    logger.warning(f"Bỏ qua giá trị không phải số: {raw_value}")
                    continue
                
                # Xử lý timestamp
                timestamp_str = point.get("created_at")
                if timestamp_str:
                    timestamp_str = timestamp_str.replace('Z', '+00:00')
                    try:
                        # Phân tích thời gian UTC
                        timestamp_utc = datetime.fromisoformat(timestamp_str)
                        # Chuyển đổi sang múi giờ local
                        timestamp_local = timestamp_utc.astimezone()
                        # Loại bỏ thông tin múi giờ để lưu vào database
                        timestamp = timestamp_local.replace(tzinfo=None)
                    except ValueError:
                        timestamp = datetime.utcnow()
                        logger.warning(f"Sử dụng thời gian hiện tại do không thể parse: {timestamp_str}")
                else:
                    timestamp = datetime.utcnow()
                    logger.warning("Không có timestamp, sử dụng thời gian hiện tại")
                
                # Tạo bản ghi mới
                new_data = SensorData(
                    device_id=device_id,
                    feed_id=feed_id,
                    value=value,
                    timestamp=timestamp
                )
                db.add(new_data)
                count += 1
                
                if count % 100 == 0:
                    logger.info(f"Đã thêm {count} bản ghi mới")
                
            except Exception as e:
                logger.error(f"Lỗi khi xử lý điểm dữ liệu: {str(e)}")
                continue
        
        db.commit()
        logger.info(f"Đã lưu {count} điểm dữ liệu mới từ feed {feed_id}")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi lưu vào database: {str(e)}")
    finally:
        db.close()
    
    return count

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Fetch data from Adafruit IO')
    parser.add_argument('--all', action='store_true', help='Fetch all data regardless of date')
    parser.add_argument('--date', type=str, help='Fetch data for specific date (format: YYYY-MM-DD)')
    parser.add_argument('--last', action='store_true', help='Fetch data for the last 1 hour')
    args = parser.parse_args()
    
    # Tạo bảng nếu chưa tồn tại
    Base.metadata.create_all(bind=engine)
    
    # Lấy danh sách feeds
    feeds = get_feeds()
    if not feeds:
        logger.error("Không thể lấy danh sách feeds. Vui lòng kiểm tra kết nối hoặc thông tin đăng nhập Adafruit IO.")
        return
    
    total_saved = 0
    
    # Xác định thời gian bắt đầu
    start_time = None
    if args.date:
        try:
            # Parse ngày từ input
            start_time = datetime.strptime(args.date, "%Y-%m-%d")
            logger.info(f"Đang lấy dữ liệu cho ngày {args.date}")
        except ValueError:
            logger.error("Định dạng ngày không hợp lệ. Vui lòng sử dụng định dạng YYYY-MM-DD (ví dụ: 2024-04-08)")
            return
    elif args.last:
        # Đơn giản hóa: Lấy dữ liệu từ 1 giờ trước
        start_time = datetime.utcnow() - timedelta(hours=1)
        logger.info(f"Đang lấy dữ liệu từ 1 giờ gần nhất (từ {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
    elif not args.all:
        # Lấy dữ liệu từ đầu ngày hôm nay
        start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"Đang lấy dữ liệu từ đầu ngày hôm nay (UTC): {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Xử lý từng feed
    for feed in feeds:
        feed_key = feed.get("key")
        if not feed_key:
            continue
            
        logger.info(f"Đang xử lý feed: {feed_key}")
        
        # Tăng limit cho trường hợp --last
        limit = 1000 if args.last else 100
        
        # Lấy dữ liệu từ feed
        data = get_feed_data(feed_key, start_time=start_time, limit=limit)
        if not data:
            logger.warning(f"Không có dữ liệu từ feed {feed_key}")
            continue
        
        # Hiển thị phạm vi thời gian của dữ liệu
        if len(data) > 0:
            first_point = data[-1]  # Điểm dữ liệu cũ nhất
            last_point = data[0]    # Điểm dữ liệu mới nhất
            
            if 'created_at' in first_point and 'created_at' in last_point:
                logger.info(f"Dải thời gian dữ liệu nhận được:")
                logger.info(f"  - Điểm cũ nhất: {first_point['created_at']}")
                logger.info(f"  - Điểm mới nhất: {last_point['created_at']}")
        
        # Lưu vào database
        saved = save_to_database(feed_key, data)
        total_saved += saved
    
    logger.info(f"Hoàn thành: Đã lưu tổng cộng {total_saved} bản ghi mới vào database")

if __name__ == "__main__":
    main() 