from sqlalchemy.orm import Session
from models import Device, Feed, User
from sqlalchemy.exc import IntegrityError

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

def add_device(device_id: str, device_type: str, admin_user_id: int, db: Session):
    # Kiểm tra device_id đã tồn tại chưa
    if db.query(Device).filter(Device.device_id == device_id).first():
        return {"success": False, "message": f"Device {device_id} đã tồn tại"}
    # Kiểm tra user là admin
    admin_user = db.query(User).filter(User.id == admin_user_id, User.role == "admin").first()
    if not admin_user:
        return {"success": False, "message": "User không phải admin hoặc không tồn tại"}
    # Tạo device mới (KHÔNG gán quyền sở hữu cho admin)
    device = Device(device_id=device_id, device_type=device_type, user_id=None)
    db.add(device)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"success": False, "message": "Lỗi khi thêm device (có thể device_id đã tồn tại)"}
    # Gắn feeds mặc định
    feeds = get_default_feeds(device_type)
    for feed_id in feeds:
        feed = Feed(device_id=device_id, feed_id=feed_id)
        db.add(feed)
    db.commit()
    return {"success": True, "message": f"Đã thêm device {device_id} với type {device_type} vào hệ thống (chưa thuộc quyền sở hữu ai)"}
