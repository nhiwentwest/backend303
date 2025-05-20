#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

# Cấu hình logging
log_file = 'remove_device.log'
log_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        log_handler
    ]
)
logger = logging.getLogger(__name__)

# Cấu hình Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5444/iot_db")

def check_tables_with_device_foreign_keys(engine, device_id):
    """
    Kiểm tra tất cả các bảng có chứa foreign key đến device_id trong bảng devices
    """
    try:
        with engine.connect() as conn:
            # Kiểm tra các bảng với cột device_id
            tables_with_references = [
                "sensor_data", 
                "original_samples", 
                "compressed_data_optimized"
            ]
            
            results = {}
            
            for table in tables_with_references:
                try:
                    result = conn.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE device_id = :device_id"),
                        {"device_id": device_id}
                    ).fetchone()
                    
                    if result and result[0] > 0:
                        results[table] = result[0]
                except Exception as e:
                    logger.warning(f"Không thể kiểm tra bảng {table}: {str(e)}")
            
            return results
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra các bảng có foreign key: {str(e)}")
        return {}

def remove_device(device_id: str, confirm: bool = False, user_id: int = None) -> dict:
    """
    Từ bỏ quyền sở hữu thiết bị (chuyển user_id về 1)
    
    Args:
        device_id: ID của thiết bị cần từ bỏ quyền sở hữu
        confirm: Xác nhận từ bỏ quyền sở hữu
        user_id: ID của người dùng hiện tại (để kiểm tra quyền sở hữu)
    
    Returns:
        dict: Kết quả từ bỏ quyền sở hữu thiết bị
    """
    try:
        # Kết nối database
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            # Bắt đầu transaction
            with conn.begin():
                # Kiểm tra thiết bị tồn tại và thuộc về người dùng
                device = conn.execute(
                    text("SELECT user_id FROM devices WHERE device_id = :device_id"),
                    {"device_id": device_id}
                ).first()
                
                if not device:
                    logger.error(f"Không tìm thấy thiết bị: {device_id}")
                    return {
                        "success": False,
                        "message": f"Không tìm thấy thiết bị: {device_id}"
                    }
                
                # Kiểm tra quyền sở hữu
                if user_id and device[0] != user_id and user_id != 1:
                    logger.error(f"Thiết bị {device_id} không thuộc về người dùng {user_id}")
                    return {
                        "success": False,
                        "message": f"Bạn không có quyền từ bỏ quyền sở hữu thiết bị này"
                    }
                
                if not confirm:
                    return {
                        "success": False,
                        "message": "Vui lòng xác nhận từ bỏ quyền sở hữu thiết bị"
                    }
                
                # Chuyển user_id về 1 (mặc định)
                result = conn.execute(
                    text("UPDATE devices SET user_id = 1 WHERE device_id = :device_id"),
                    {"device_id": device_id}
                )
                
                if result.rowcount > 0:
                    logger.info(f"Đã chuyển thiết bị {device_id} về người dùng mặc định (user_id = 1)")
                    return {
                        "success": True,
                        "message": f"Đã từ bỏ quyền sở hữu thiết bị {device_id}",
                        "device_id": device_id
                    }
                else:
                    logger.error(f"Không thể cập nhật thiết bị {device_id}")
                    return {
                        "success": False,
                        "message": f"Không thể từ bỏ quyền sở hữu thiết bị {device_id}"
                    }
        
    except Exception as e:
        logger.error(f"Lỗi khi từ bỏ quyền sở hữu thiết bị {device_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Lỗi: {str(e)}"
        }

def main():
    parser = argparse.ArgumentParser(description="Xóa thiết bị và tất cả dữ liệu liên quan từ database")
    parser.add_argument("--device-id", type=str, required=True, help="ID của thiết bị cần xóa")
    parser.add_argument("--confirm", action="store_true", help="Xác nhận xóa mà không cần hỏi lại")
    parser.add_argument("--user-id", type=int, help="ID của người dùng yêu cầu xóa thiết bị (để kiểm tra quyền sở hữu)")
    
    args = parser.parse_args()
    
    result = remove_device(args.device_id, args.confirm, args.user_id)
    
    if result["success"]:
        print("="*80)
        print(f"ĐÃ XÓA THÀNH CÔNG THIẾT BỊ: {args.device_id}")
        print("="*80)
        if "deleted_counts" in result:
            for table, count in result["deleted_counts"].items():
                print(f"- {table}: {count} bản ghi")
    else:
        print("="*80)
        print(f"KHÔNG THỂ XÓA THIẾT BỊ: {args.device_id}")
        print(f"Lý do: {result['message']}")
        print("="*80)
        if "owner_id" in result:
            print(f"Thiết bị thuộc về người dùng ID: {result['owner_id']}")

if __name__ == "__main__":
    main()
