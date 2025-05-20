#!/usr/bin/env python3
"""
Script để đổi tên device_id
"""

import os
import logging
import argparse
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from typing import Dict, Any

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def rename_device(old_device_id: str, new_device_id: str) -> Dict[str, Any]:
    """
    Đổi tên device_id của một thiết bị
    
    Args:
        old_device_id: ID cũ của thiết bị
        new_device_id: ID mới của thiết bị
        
    Returns:
        Dict chứa thông tin về kết quả thực hiện
    """
    logger.info(f"Bắt đầu đổi tên thiết bị từ {old_device_id} sang {new_device_id}")
    
    try:
        # Load biến môi trường
        load_dotenv()
        
        # Cấu hình Database
        DATABASE_URL = os.getenv("DATABASE_URL")
        engine = create_engine(DATABASE_URL)
        
        # Kết nối database
        connection = engine.connect()
        
        # 1. Kiểm tra thiết bị cũ có tồn tại không
        result = connection.execute(
            text("SELECT id, device_id FROM devices WHERE device_id = :device_id"),
            {"device_id": old_device_id}
        ).fetchone()
        
        if not result:
            logger.error(f"Không tìm thấy thiết bị với ID: {old_device_id}")
            return {
                "success": False,
                "error": f"Không tìm thấy thiết bị với ID: {old_device_id}"
            }
        
        device_id = result[1]
        logger.info(f"Đã tìm thấy thiết bị: {device_id}")
        
        # 2. Kiểm tra device mới đã tồn tại chưa
        result = connection.execute(
            text("SELECT id FROM devices WHERE device_id = :device_id"),
            {"device_id": new_device_id}
        ).fetchone()
        
        if result:
            raise ValueError(f"Device_id {new_device_id} đã tồn tại")
        
        logger.info(f"Device_id mới {new_device_id} chưa tồn tại, có thể sử dụng")
        
        # 3. Tạo device mới
        try:
            # Tạo device mới với user_id = NULL
            connection.execute(
                text("""
                    INSERT INTO devices (device_id, user_id)
                    VALUES (:device_id, NULL)
                """),
                {
                    "device_id": new_device_id
                }
            )
        except Exception as e:
            # Nếu không thể chèn NULL (ví dụ: ràng buộc chưa được cập nhật)
            logger.warning(f"Không thể chèn với user_id = NULL: {str(e)}")
            # Thử lại với user_id mặc định
            connection.execute(
                text("""
                    INSERT INTO devices (device_id, user_id)
                    VALUES (:device_id, 1)
                """),
                {
                    "device_id": new_device_id
                }
            )
        logger.info(f"Đã tạo device mới: {new_device_id}")
        
        # 4. Cập nhật tên trong bảng sensor_data
        connection.execute(
            text("UPDATE sensor_data SET device_id = :new_device_id WHERE device_id = :old_device_id"),
            {"new_device_id": new_device_id, "old_device_id": old_device_id}
        )
        logger.info(f"Đã cập nhật device_id trong bảng sensor_data")
        
        # 5. Cập nhật tên trong bảng original_samples
        connection.execute(
            text("UPDATE original_samples SET device_id = :new_device_id WHERE device_id = :old_device_id"),
            {"new_device_id": new_device_id, "old_device_id": old_device_id}
        )
        logger.info(f"Đã cập nhật device_id trong bảng original_samples")
        
        # 6. Cập nhật tên trong bảng compressed_data_optimized
        connection.execute(
            text("UPDATE compressed_data_optimized SET device_id = :new_device_id WHERE device_id = :old_device_id"),
            {"new_device_id": new_device_id, "old_device_id": old_device_id}
        )
        logger.info(f"Đã cập nhật device_id trong bảng compressed_data_optimized")
        
        # 7. Cập nhật tên trong bảng feeds
        try:
            mapping_count = connection.execute(
                text("SELECT COUNT(*) FROM feeds WHERE device_id = :old_device_id"),
                {"old_device_id": old_device_id}
            ).scalar()
            
            if mapping_count and mapping_count > 0:
                connection.execute(
                    text("UPDATE feeds SET device_id = :new_device_id WHERE device_id = :old_device_id"),
                    {"new_device_id": new_device_id, "old_device_id": old_device_id}
                )
                connection.commit()
                logger.info(f"Đã cập nhật {mapping_count} bản ghi trong bảng feeds")
        except Exception as e:
            logger.warning(f"Không thể cập nhật dữ liệu từ feeds: {str(e)}")
        
        # 8. Xóa device cũ
        connection.execute(
            text("DELETE FROM devices WHERE device_id = :old_device_id"),
            {"old_device_id": old_device_id}
        )
        logger.info(f"Đã xóa device cũ: {old_device_id}")
        
        logger.info(f"Đã đổi tên device_id từ '{old_device_id}' thành '{new_device_id}' thành công")
        
        return {
            "success": True,
            "message": f"Đã đổi tên device_id từ '{old_device_id}' thành '{new_device_id}' thành công"
        }
    except Exception as e:
        logger.error(f"Lỗi khi đổi tên device_id: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Đổi tên device_id')
    parser.add_argument('old_device_id', help='Device_id cũ')
    parser.add_argument('new_device_id', help='Device_id mới')
    args = parser.parse_args()
    
    rename_device(args.old_device_id, args.new_device_id) 