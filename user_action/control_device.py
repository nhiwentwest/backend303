import logging
import requests
import os
from sqlalchemy import text
from database import get_db
from dotenv import load_dotenv
import datetime
from user_action.device_features import DEVICE_FEATURES

# Tải biến môi trường từ file .env
load_dotenv()

# Lấy thông tin xác thực Adafruit IO từ biến môi trường
ADAFRUIT_IO_USERNAME = os.getenv('ADAFRUIT_IO_USERNAME')
ADAFRUIT_IO_KEY = os.getenv('ADAFRUIT_IO_KEY')

# Cấu hình logging
logger = logging.getLogger(__name__)

def send_to_adafruit(feed_id, value):
    """
    Gửi dữ liệu lên Adafruit IO
    
    Args:
        feed_id (str): ID của feed trên Adafruit IO
        value (int/str): Giá trị cần gửi (0 hoặc 1)
    
    Returns:
        dict: Kết quả của việc gửi dữ liệu
    """
    if not ADAFRUIT_IO_USERNAME or not ADAFRUIT_IO_KEY:
        logger.error("Thiếu thông tin xác thực Adafruit IO trong file .env")
        return {
            "success": False,
            "message": "Không thể kết nối với Adafruit IO: Thiếu thông tin xác thực"
        }
    
    try:
        # Lấy thời gian hiện tại của máy local
        local_timestamp = datetime.datetime.now()
        formatted_timestamp = local_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        
        # Log thông tin xác thực (chỉ để debug)
        logger.info(f"Sử dụng Adafruit IO Username: {ADAFRUIT_IO_USERNAME}")
        logger.info(f"API Key prefix: {ADAFRUIT_IO_KEY[:5]}...")
        logger.info(f"Thời gian local gửi dữ liệu: {formatted_timestamp}")
        
        # URL cho Adafruit IO REST API
        url = f"https://io.adafruit.com/api/v2/{ADAFRUIT_IO_USERNAME}/feeds/{feed_id}/data"
        
        # Kiểm tra feed tồn tại trước
        check_url = f"https://io.adafruit.com/api/v2/{ADAFRUIT_IO_USERNAME}/feeds/{feed_id}"
        logger.info(f"Kiểm tra feed có tồn tại: {check_url}")
        
        headers = {
            'X-AIO-Key': ADAFRUIT_IO_KEY,
            'Content-Type': 'application/json'
        }
        
        # Kiểm tra feed tồn tại
        try:
            check_response = requests.get(check_url, headers=headers)
            if check_response.status_code != 200:
                logger.error(f"Feed {feed_id} không tồn tại: {check_response.status_code} - {check_response.text}")
                return {
                    "success": False,
                    "message": f"Feed {feed_id} không tồn tại trên Adafruit IO",
                    "details": check_response.text
                }
        except Exception as e:
            logger.warning(f"Lỗi khi kiểm tra feed tồn tại: {str(e)}")
            # Tiếp tục xử lý
        
        # Dữ liệu cần gửi
        data = {
            'value': value
        }
        
        logger.info(f"Đang gửi request đến: {url}")
        # Gửi request POST
        response = requests.post(url, json=data, headers=headers)
        
        # Kiểm tra kết quả
        if response.status_code in [200, 201]:
            response_data = response.json()
            logger.info(f"Gửi dữ liệu thành công lên feed {feed_id}: {value}")
            
            # Chuyển đổi thời gian Adafruit từ UTC sang múi giờ local
            adafruit_time_str = response_data.get('created_at')
            if adafruit_time_str:
                try:
                    # Phân tích thời gian UTC từ Adafruit
                    adafruit_time_utc = datetime.datetime.strptime(adafruit_time_str, "%Y-%m-%dT%H:%M:%SZ")
                    # Thêm thông tin múi giờ UTC
                    adafruit_time_utc = adafruit_time_utc.replace(tzinfo=datetime.timezone.utc)
                    # Chuyển đổi sang múi giờ local
                    adafruit_time_local = adafruit_time_utc.astimezone()
                    # Format lại thời gian để hiển thị
                    adafruit_time_formatted = adafruit_time_local.strftime("%Y-%m-%d %H:%M:%S %z")
                    
                    logger.info(f"Thời gian Adafruit (UTC): {adafruit_time_str}")
                    logger.info(f"Thời gian Adafruit (local): {adafruit_time_formatted}")
                    
                    # Lưu thời gian đã chuyển đổi vào response_data
                    response_data['created_at_local'] = adafruit_time_formatted
                except Exception as e:
                    logger.warning(f"Không thể chuyển đổi múi giờ: {str(e)}")
            
            return {
                "success": True,
                "message": "Gửi dữ liệu lên Adafruit IO thành công",
                "response": response_data,
                "local_timestamp": local_timestamp
            }
        else:
            logger.error(f"Lỗi khi gửi dữ liệu lên Adafruit IO: {response.status_code} - {response.text}")
            return {
                "success": False,
                "message": f"Lỗi khi gửi dữ liệu lên Adafruit IO: {response.status_code}",
                "details": response.text
            }
    except Exception as e:
        logger.error(f"Ngoại lệ khi gửi dữ liệu lên Adafruit IO: {str(e)}")
        return {
            "success": False,
            "message": f"Không thể kết nối với Adafruit IO: {str(e)}"
        }

def control_device(device_id, user_id, feature, value):
    logger.info(f"Yêu cầu điều khiển thiết bị: device_id={device_id}, user_id={user_id}, feature={feature}, value={value}")
    db = next(get_db())
    try:
        # Kiểm tra quyền sở hữu thiết bị
        check_query = text("""
        SELECT id, device_type FROM devices 
        WHERE device_id = :device_id AND user_id = :user_id
        """)
        result = db.execute(check_query, {"device_id": device_id, "user_id": user_id})
        device = result.fetchone()
        if not device:
            logger.warning(f"Người dùng {user_id} không sở hữu thiết bị {device_id}")
            return {"success": False, "message": f"Thiết bị {device_id} không tồn tại hoặc bạn không có quyền điều khiển nó"}
        # Lấy device_type từ bảng devices
        device_type = device[1]
        features = DEVICE_FEATURES.get(device_type)
        if not features:
            return {"success": False, "message": "Thiết bị không hỗ trợ điều khiển"}
        feature_info = next((f for f in features if f["feature"] == feature), None)
        if not feature_info:
            return {"success": False, "message": "Tính năng không hợp lệ cho thiết bị này"}
        # Kiểm tra value hợp lệ
        if feature_info["type"] == "toggle" and value not in feature_info["values"]:
            return {"success": False, "message": "Giá trị không hợp lệ"}
        if feature_info["type"] == "slider":
            if not (feature_info["min"] <= value <= feature_info["max"]):
                return {"success": False, "message": "Giá trị ngoài phạm vi cho phép"}
        # Kiểm tra feed_id có thuộc về device_id không
        feed_id = feature_info["feed"]
        feed_query = text("""
            SELECT 1 FROM feeds WHERE device_id = :device_id AND feed_id = :feed_id
        """)
        feed_exists = db.execute(feed_query, {"device_id": device_id, "feed_id": feed_id}).first()
        if not feed_exists:
            logger.warning(f"Feed {feed_id} không thuộc về device_id {device_id}")
            return {"success": False, "message": f"Feed {feed_id} không thuộc về thiết bị {device_id}"}
        # Gửi lệnh lên đúng feed
        adafruit_result = send_to_adafruit(feed_id, value)
        return {
            "success": adafruit_result["success"],
            "message": adafruit_result["message"],
            "device_id": device_id,
            "feature": feature,
            "feed_id": feed_id,
            "value": value,
            "adafruit_response": adafruit_result.get("response", {})
        }
    except Exception as e:
        logger.error(f"Lỗi khi xử lý yêu cầu điều khiển thiết bị: {str(e)}")
        return {
            "success": False,
            "message": f"Lỗi hệ thống: {str(e)}"
        }
    finally:
        db.close()
