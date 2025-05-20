#!/usr/bin/env python3
"""
Script để đổi tên device_id của người dùng
"""

import os
import logging
import argparse
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from sqlalchemy.orm import Session
import models
from typing import Dict, Any

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_FEEDS = {
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
}

def assign_default_feeds(conn, device_id, device_type):
    feeds = DEFAULT_FEEDS.get(device_type, [])
    for feed_id in feeds:
        exists = conn.execute(
            text("SELECT 1 FROM feeds WHERE device_id = :device_id AND feed_id = :feed_id"),
            {"device_id": device_id, "feed_id": feed_id}
        ).first()
        if not exists:
            conn.execute(
                text("INSERT INTO feeds (device_id, feed_id) VALUES (:device_id, :feed_id)"),
                {"device_id": device_id, "feed_id": feed_id}
            )
    conn.commit()

def check_device_ownership(device_id: str, user_id: int, db: Session) -> bool:
    """
    Kiểm tra xem người dùng có sở hữu thiết bị không
    
    Args:
        device_id: ID của thiết bị
        user_id: ID của người dùng
        db: Database session
        
    Returns:
        bool: True nếu người dùng sở hữu thiết bị, False nếu không
    """
    try:
        device = db.query(models.Device).filter(
            models.Device.device_id == device_id,
            models.Device.user_id == user_id
        ).first()
        
        return device is not None
        
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra quyền sở hữu thiết bị: {str(e)}")
        return False

def rename_device(old_device_id: str, new_device_id: str, user_id: int) -> Dict[str, Any]:
    """
    Đổi tên device_id của người dùng.
    Cho phép đổi tên thành device đã tồn tại nếu người dùng sở hữu cả hai thiết bị.
    Khi đó, dữ liệu từ thiết bị cũ sẽ được gộp vào thiết bị mới.
    
    Args:
        old_device_id: ID cũ của thiết bị
        new_device_id: ID mới của thiết bị
        user_id: ID của người dùng thực hiện đổi tên
        
    Returns:
        dict: Kết quả đổi tên thiết bị
    """
    logger.info(f"Bắt đầu đổi tên device_id từ {old_device_id} sang {new_device_id} bởi user_id={user_id}")
    
    try:
        # Tạo session mới
        from database import SessionLocal
        db = SessionLocal()
        
        try:
            # Kiểm tra quyền sở hữu thiết bị cũ
            if not check_device_ownership(old_device_id, user_id, db):
                logger.warning(f"Người dùng {user_id} không sở hữu thiết bị {old_device_id}")
                return {
                    "success": False,
                    "message": f"Bạn không có quyền đổi tên thiết bị {old_device_id}"
                }
            
            # Kiểm tra xem new_device_id đã tồn tại chưa
            device_exists = db.execute(
                text("SELECT device_id, user_id FROM devices WHERE device_id = :device_id"),
                {"device_id": new_device_id}
            ).fetchone()
            
            # Nếu thiết bị mới đã tồn tại
            if device_exists:
                current_owner_id = device_exists[1]
                
                # Nếu thiết bị mới không thuộc về người dùng hiện tại
                if current_owner_id != user_id:
                    logger.warning(f"Thiết bị {new_device_id} đã tồn tại và thuộc về người dùng khác (user_id={current_owner_id})")
                    return {
                        "success": False,
                        "message": f"Device_id {new_device_id} đã tồn tại và thuộc về người dùng khác"
                    }
                
                # Nếu thiết bị mới thuộc về người dùng hiện tại, thực hiện gộp dữ liệu
                logger.info(f"Device_id {new_device_id} đã tồn tại và thuộc về người dùng hiện tại (user_id={user_id})")
                logger.info(f"Thực hiện gộp dữ liệu từ {old_device_id} vào {new_device_id}")
                
                # BẮT ĐẦU TRANSACTION MỚI
                transaction_successful = True
                
                # 1. Xử lý bảng feeds trước tiên (quan trọng vì có ràng buộc khóa ngoại)
                try:
                    # Kiểm tra xem có feed nào từ thiết bị cũ không
                    mapping_count = db.execute(
                        text("SELECT COUNT(*) FROM feeds WHERE device_id = :old_device_id"),
                        {"old_device_id": old_device_id}
                    ).scalar() or 0
                    
                    if mapping_count > 0:
                        logger.info(f"Tìm thấy {mapping_count} feed từ thiết bị cũ {old_device_id}")
                        
                        # Lấy danh sách feed từ thiết bị cũ
                        old_feeds = db.execute(
                            text("SELECT feed_id FROM feeds WHERE device_id = :old_device_id"),
                            {"old_device_id": old_device_id}
                        ).fetchall()
                        
                        old_feed_ids = [feed[0] for feed in old_feeds]
                        logger.info(f"Danh sách feed từ thiết bị cũ: {old_feed_ids}")
                        
                        # Lấy danh sách feed từ thiết bị mới
                        new_feeds = db.execute(
                            text("SELECT feed_id FROM feeds WHERE device_id = :new_device_id"),
                            {"new_device_id": new_device_id}
                        ).fetchall()
                        
                        new_feed_ids = [feed[0] for feed in new_feeds]
                        logger.info(f"Danh sách feed từ thiết bị mới: {new_feed_ids}")
                        
                        # Tìm các feed trùng lặp
                        duplicate_feed_ids = list(set(old_feed_ids) & set(new_feed_ids))
                        
                        if duplicate_feed_ids:
                            logger.warning(f"Phát hiện {len(duplicate_feed_ids)} feed bị trùng: {duplicate_feed_ids}")
                            
                            # THAY ĐỔI: Không cập nhật sensor_data, chỉ xóa feeds trùng lặp
                            # Xóa các feed trùng lặp từ thiết bị cũ
                            for feed_id in duplicate_feed_ids:
                                db.execute(
                                    text("DELETE FROM feeds WHERE device_id = :old_device_id AND feed_id = :feed_id"),
                                    {"old_device_id": old_device_id, "feed_id": feed_id}
                                )
                                logger.info(f"Đã xóa feed trùng lặp: {feed_id} từ thiết bị {old_device_id}")
                            
                        # Lấy danh sách feed không trùng lặp
                        non_duplicate_feeds = list(set(old_feed_ids) - set(new_feed_ids))
                        
                        if non_duplicate_feeds:
                            logger.info(f"Cập nhật {len(non_duplicate_feeds)} feed không trùng lặp")
                            
                            # Tạo placeholder cho danh sách feed
                            placeholders = ','.join([f"'{feed_id}'" for feed_id in non_duplicate_feeds])
                            
                            # Cập nhật các feed không trùng lặp
                            query = text(f"""
                                UPDATE feeds 
                                SET device_id = :new_device_id 
                                WHERE device_id = :old_device_id 
                                AND feed_id IN ({placeholders})
                            """)
                            
                            db.execute(
                                query,
                                {"new_device_id": new_device_id, "old_device_id": old_device_id}
                            )
                            
                            logger.info(f"Đã cập nhật {len(non_duplicate_feeds)} feed từ {old_device_id} sang {new_device_id}")
                        
                        # Commit thay đổi cho bảng feeds
                        db.commit()
                    else:
                        logger.info(f"Không tìm thấy feed nào từ thiết bị cũ {old_device_id}")
                        
                except Exception as e:
                    db.rollback()
                    logger.error(f"Lỗi khi cập nhật feeds: {str(e)}")
                    transaction_successful = False
                
                # THAY ĐỔI: Bỏ qua phần cập nhật bảng sensor_data
                logger.info("Bỏ qua cập nhật sensor_data, việc này sẽ được xử lý bởi fetch.py")
                
                # 3. Cập nhật các bảng khác
                if transaction_successful:
                    try:
                        # Cập nhật original_samples
                        original_samples_count = db.execute(
                            text("SELECT COUNT(*) FROM original_samples WHERE device_id = :old_device_id"),
                            {"old_device_id": old_device_id}
                        ).scalar() or 0
                        
                        if original_samples_count > 0:
                            db.execute(
                                text("UPDATE original_samples SET device_id = :new_device_id WHERE device_id = :old_device_id"),
                                {"new_device_id": new_device_id, "old_device_id": old_device_id}
                            )
                            db.commit()
                            logger.info(f"Đã cập nhật {original_samples_count} bản ghi trong bảng original_samples")
                        
                        # BỔ SUNG: Cập nhật compressed_data_optimized
                        compressed_count = db.execute(
                            text("SELECT COUNT(*) FROM compressed_data_optimized WHERE device_id = :old_device_id"),
                            {"old_device_id": old_device_id}
                        ).scalar() or 0
                        if compressed_count > 0:
                            db.execute(
                                text("UPDATE compressed_data_optimized SET device_id = :new_device_id WHERE device_id = :old_device_id"),
                                {"new_device_id": new_device_id, "old_device_id": old_device_id}
                            )
                            db.commit()
                            logger.info(f"Đã cập nhật {compressed_count} bản ghi trong bảng compressed_data_optimized")
                        
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Lỗi khi cập nhật các bảng khác: {str(e)}")
                        transaction_successful = False
                
                # 4. Xóa thiết bị cũ chỉ khi tất cả các bước trước thành công
                if transaction_successful:
                    try:
                        # Kiểm tra lại xem còn dữ liệu nào tham chiếu đến thiết bị cũ không
                        remaining_feeds = db.execute(
                            text("SELECT COUNT(*) FROM feeds WHERE device_id = :old_device_id"),
                            {"old_device_id": old_device_id}
                        ).scalar() or 0
                        
                        if remaining_feeds > 0:
                            logger.warning(f"Vẫn còn dữ liệu tham chiếu đến thiết bị cũ: {remaining_feeds} feeds")
                            logger.warning("Không thể xóa thiết bị cũ an toàn, bỏ qua bước này")
                        else:
                            db.execute(
                                text("DELETE FROM devices WHERE device_id = :old_device_id"),
                                {"old_device_id": old_device_id}
                            )
                            db.commit()
                            logger.info(f"Đã xóa thiết bị cũ: {old_device_id}")
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Lỗi khi xóa thiết bị cũ: {str(e)}")
                        transaction_successful = False
                
                if transaction_successful:
                    return {
                        "success": True,
                        "message": f"Đã gộp dữ liệu từ '{old_device_id}' vào '{new_device_id}' thành công"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Đã xảy ra lỗi trong quá trình gộp dữ liệu, vui lòng kiểm tra logs để biết thêm chi tiết"
                    }
                
            else:
                # Nếu thiết bị mới chưa tồn tại, thực hiện đổi tên như bình thường
                # THAY ĐỔI: Tạo thiết bị mới trước, sau đó cập nhật các bảng phụ thuộc

                # 1. Tạo thiết bị mới với các thuộc tính giống thiết bị cũ
                try:
                    # Lấy thông tin của thiết bị cũ
                    device_info = db.execute(
                        text("SELECT user_id FROM devices WHERE device_id = :device_id"),
                        {"device_id": old_device_id}
                    ).fetchone()
                    
                    # Tạo thiết bị mới
                    db.execute(
                        text("""
                            INSERT INTO devices (device_id, user_id)
                            VALUES (:new_device_id, :user_id)
                        """),
                        {"new_device_id": new_device_id, "user_id": device_info[0]}
                    )
                    db.commit()
                    logger.info(f"Đã tạo thiết bị mới: {new_device_id}")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Lỗi khi tạo thiết bị mới: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Lỗi khi tạo thiết bị mới: {str(e)}"
                    }
                
                # THAY ĐỔI: Bỏ qua phần cập nhật bảng sensor_data
                logger.info("Bỏ qua cập nhật sensor_data, việc này sẽ được xử lý bởi fetch.py")
                
                # 3. Cập nhật bảng feeds
                feeds_updated = True
                try:
                    mapping_count = db.execute(
                        text("SELECT COUNT(*) FROM feeds WHERE device_id = :old_device_id"),
                        {"old_device_id": old_device_id}
                    ).scalar() or 0
                    
                    if mapping_count > 0:
                        db.execute(
                            text("UPDATE feeds SET device_id = :new_device_id WHERE device_id = :old_device_id"),
                            {"new_device_id": new_device_id, "old_device_id": old_device_id}
                        )
                        db.commit()
                        logger.info(f"Đã cập nhật {mapping_count} bản ghi trong bảng feeds")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Lỗi khi cập nhật feeds: {str(e)}")
                    feeds_updated = False
                
                # 4. Cập nhật các bảng khác
                try:
                    # Cập nhật original_samples
                    original_samples_count = db.execute(
                        text("SELECT COUNT(*) FROM original_samples WHERE device_id = :old_device_id"),
                        {"old_device_id": old_device_id}
                    ).scalar() or 0
                    
                    if original_samples_count > 0:
                        db.execute(
                            text("UPDATE original_samples SET device_id = :new_device_id WHERE device_id = :old_device_id"),
                            {"new_device_id": new_device_id, "old_device_id": old_device_id}
                        )
                        db.commit()
                        logger.info(f"Đã cập nhật {original_samples_count} bản ghi trong bảng original_samples")
                        
                    # BỔ SUNG: Cập nhật compressed_data_optimized
                    compressed_count = db.execute(
                        text("SELECT COUNT(*) FROM compressed_data_optimized WHERE device_id = :old_device_id"),
                        {"old_device_id": old_device_id}
                    ).scalar() or 0
                    if compressed_count > 0:
                        db.execute(
                            text("UPDATE compressed_data_optimized SET device_id = :new_device_id WHERE device_id = :old_device_id"),
                            {"new_device_id": new_device_id, "old_device_id": old_device_id}
                        )
                        db.commit()
                        logger.info(f"Đã cập nhật {compressed_count} bản ghi trong bảng compressed_data_optimized")
                    
                except Exception as e:
                    logger.warning(f"Lỗi khi cập nhật các bảng khác: {str(e)}")
                
                # 5. Xóa thiết bị cũ nếu mọi thứ đã cập nhật thành công
                if feeds_updated:
                    try:
                        db.execute(
                            text("DELETE FROM devices WHERE device_id = :old_device_id"),
                            {"old_device_id": old_device_id}
                        )
                        db.commit()
                        logger.info(f"Đã xóa thiết bị cũ: {old_device_id}")
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Lỗi khi xóa thiết bị cũ: {str(e)}")
                
                return {
                    "success": feeds_updated,
                    "message": f"Đã đổi tên device_id từ '{old_device_id}' thành '{new_device_id}' thành công" if feeds_updated else "Lỗi khi cập nhật dữ liệu, không thể đổi tên device_id hoàn toàn"
                }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi đổi tên device_id: {str(e)}")
            raise
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Lỗi khi đổi tên device_id: {str(e)}")
        return {
            "success": False,
            "message": f"Lỗi khi đổi tên device_id: {str(e)}"
        }

def claim_device(device_id: str, user_id: int) -> None:
    """
    Yêu cầu sở hữu một thiết bị.
    Sau khi claim, luôn kiểm tra và tự động gán feed mặc định dựa trên device_type.
    """
    try:
        from database import engine
        with engine.connect() as conn:
            # Lấy user_id và device_type hiện tại
            result = conn.execute(
                text("SELECT user_id, device_type FROM devices WHERE device_id = :device_id"),
                {"device_id": device_id}
            )
            device = result.first()
            if not device:
                raise ValueError("Thiết bị không tồn tại")
            current_user_id = device[0]
            device_type = device[1] or "yolo-device"
            if current_user_id is not None and current_user_id != user_id:
                raise ValueError("Thiết bị đã có chủ sở hữu khác")
            # Nếu chưa thuộc về user này thì cập nhật user_id
            if current_user_id != user_id:
                conn.execute(
                    text("""
                        UPDATE devices 
                        SET user_id = :user_id 
                        WHERE device_id = :device_id
                    """),
                    {"device_id": device_id, "user_id": user_id}
                )
                conn.commit()
            assign_default_feeds(conn, device_id, device_type)
    except Exception as e:
        logger.error(f"Lỗi khi yêu cầu sở hữu thiết bị: {str(e)}")
        raise

def remove_device(device_id: str, user_id: int) -> None:
    """
    Từ bỏ quyền sở hữu một thiết bị.
    
    Args:
        device_id: ID của thiết bị cần từ bỏ quyền sở hữu
        user_id: ID của người dùng đang sở hữu thiết bị
        
    Raises:
        ValueError: Nếu người dùng không sở hữu thiết bị
    """
    try:
        # Kết nối database
        from database import engine
        with engine.connect() as conn:
            # Kiểm tra quyền sở hữu thiết bị
            result = conn.execute(
                text("""
                    SELECT user_id 
                    FROM devices 
                    WHERE device_id = :device_id
                """),
                {"device_id": device_id}
            )
            device = result.first()
            
            if not device:
                raise ValueError("Thiết bị không tồn tại")
                
            current_user_id = device[0]
            
            # Kiểm tra người dùng có sở hữu thiết bị không
            if current_user_id != user_id:
                raise ValueError("Bạn không có quyền từ bỏ thiết bị này")
                
            # Cập nhật user_id về NULL (chưa có chủ sở hữu)
            conn.execute(
                text("""
                    UPDATE devices 
                    SET user_id = NULL 
                    WHERE device_id = :device_id
                """),
                {"device_id": device_id}
            )
            conn.commit()
            
    except Exception as e:
        logger.error(f"Lỗi khi từ bỏ quyền sở hữu thiết bị: {str(e)}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Đổi tên device_id của người dùng')
    parser.add_argument('old_device_id', help='Device_id cũ')
    parser.add_argument('new_device_id', help='Device_id mới')
    parser.add_argument('user_id', type=int, help='ID của người dùng')
    args = parser.parse_args()
    
    rename_device(args.old_device_id, args.new_device_id, args.user_id)
