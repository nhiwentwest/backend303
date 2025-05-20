from sqlalchemy.orm import Session
from models import Device, OriginalSamples, CompressedDataOptimized, SensorData

def delete_device(device_id: str, db: Session):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        return {"success": False, "message": f"Device {device_id} không tồn tại"}
    try:
        # Xoá dữ liệu liên quan
        db.query(OriginalSamples).filter(OriginalSamples.device_id == device_id).delete()
        db.query(CompressedDataOptimized).filter(CompressedDataOptimized.device_id == device_id).delete()
        db.query(SensorData).filter(SensorData.device_id == device_id).delete()
        # Xoá device
        db.delete(device)
        db.commit()
        return {"success": True, "message": f"Đã xoá device {device_id} và toàn bộ dữ liệu liên quan (feeds và user không bị ảnh hưởng)"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"Lỗi khi xoá device: {str(e)}"}
