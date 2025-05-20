#!/usr/bin/env python3
"""
Script đổi device_type cho device và tự động cập nhật feeds tương ứng.
Usage: python type.py <device-id> <device-type>
"""
import sys
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load biến môi trường
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL chưa được cấu hình trong .env!")
    sys.exit(1)

def get_default_feeds(device_type):
    return {
        "yolo-fan": [
            "yolo-fan",
            "yolo-fan-mode-select",
            "temperature-var",
            "yolo-fan-speed"
        ],
        "yolo-light": [
            "yolo-led",
            "yolo-led-mode-select",
            "light-var",
            "yolo-led-num"
        ],
        "yolo-device": []
    }.get(device_type, [])

def update_device_type_and_feeds(device_id, device_type):
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Kiểm tra device tồn tại
        result = conn.execute(
            text("SELECT device_id FROM devices WHERE device_id = :device_id"),
            {"device_id": device_id}
        ).first()
        if not result:
            logger.error(f"Thiết bị {device_id} không tồn tại!")
            return
        # Cập nhật device_type
        conn.execute(
            text("UPDATE devices SET device_type = :device_type WHERE device_id = :device_id"),
            {"device_id": device_id, "device_type": device_type}
        )
        logger.info(f"Đã cập nhật device_type cho {device_id} thành {device_type}")
        # Xoá toàn bộ feed cũ của device này
        conn.execute(
            text("DELETE FROM feeds WHERE device_id = :device_id"),
            {"device_id": device_id}
        )
        logger.info(f"Đã xoá toàn bộ feeds cũ của {device_id}")
        # Gán feed mới
        feeds = get_default_feeds(device_type)
        for feed_id in feeds:
            conn.execute(
                text("INSERT INTO feeds (device_id, feed_id) VALUES (:device_id, :feed_id)"),
                {"device_id": device_id, "feed_id": feed_id}
            )
            logger.info(f"Đã gán feed {feed_id} cho {device_id}")
        conn.commit()
        logger.info(f"Hoàn tất cập nhật feeds cho {device_id} với device_type {device_type}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python type.py <device-id> <device-type>")
        print("device-type: yolo-fan | yolo-light | yolo-device")
        sys.exit(1)
    device_id = sys.argv[1]
    device_type = sys.argv[2]
    if device_type not in ["yolo-fan", "yolo-light", "yolo-device"]:
        logger.error("device-type phải là: yolo-fan, yolo-light, hoặc yolo-device")
        sys.exit(1)
    update_device_type_and_feeds(device_id, device_type)

if __name__ == "__main__":
    main()
