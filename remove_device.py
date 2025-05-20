#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load biến môi trường
load_dotenv()

# Kết nối database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5444/iot_db")

def remove_device(device_id: str) -> dict:
    """
    Loại bỏ quyền sở hữu của người dùng đối với thiết bị
    
    Args:
        device_id: ID của thiết bị cần loại bỏ quyền sở hữu
    
    Returns:
        dict: Kết quả xử lý với số lượng bản ghi đã cập nhật
    """
    try:
        # Kết nối database
        engine = create_engine(DATABASE_URL)
        updated_data = {}
        
        with engine.connect() as conn:
            # Bắt đầu transaction
            with conn.begin():
                # Kiểm tra thiết bị tồn tại
                device = conn.execute(
                    text("SELECT id, user_id FROM devices WHERE device_id = :device_id"),
                    {"device_id": device_id}
                ).first()
                
                if not device:
                    logger.error(f"Không tìm thấy thiết bị: {device_id}")
                    return {
                        "success": False,
                        "message": f"Không tìm thấy thiết bị: {device_id}"
                    }
                
                # Lưu user_id hiện tại để hiển thị trong logs
                current_user_id = device[1]
                
                # Loại bỏ quyền sở hữu của người dùng (đặt user_id = NULL)
                if current_user_id is not None:
                    result = conn.execute(
                        text("UPDATE devices SET user_id = NULL WHERE device_id = :device_id"),
                        {"device_id": device_id}
                    )
                    updated_data["devices"] = result.rowcount
                    logger.info(f"Đã loại bỏ quyền sở hữu của user_id {current_user_id} đối với thiết bị {device_id}")
                else:
                    logger.info(f"Thiết bị {device_id} hiện không thuộc sở hữu của bất kỳ người dùng nào")
                    updated_data["devices"] = 0
        
        return {
            "success": True,
            "message": f"Đã loại bỏ quyền sở hữu của người dùng đối với thiết bị {device_id} thành công",
            "updated_counts": updated_data
        }
        
    except Exception as e:
        logger.error(f"Lỗi khi xử lý thiết bị {device_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Lỗi khi xử lý thiết bị: {str(e)}"
        }

def main():
    """
    Hàm main để chạy script từ command line
    """
    if len(sys.argv) != 2:
        print("Sử dụng: python remove_device.py <device_id>")
        sys.exit(1)
    
    device_id = sys.argv[1]
    print(f"Đang loại bỏ quyền sở hữu của người dùng đối với thiết bị {device_id}...")
    
    result = remove_device(device_id)
    
    if result["success"]:
        print("Kết quả xử lý:")
        print(f"- Thiết bị đã loại bỏ quyền sở hữu: {result['updated_counts'].get('devices', 0)}")
    else:
        print(f"Lỗi: {result['message']}")
        sys.exit(1)

if __name__ == "__main__":
    main() 