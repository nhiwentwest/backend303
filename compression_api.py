#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API cho các tính năng nén dữ liệu.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
from typing import Dict, Any, List, Optional
from database import get_db
import models

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tạo router
router = APIRouter(
    prefix="/compression",
    tags=["compression"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
def read_root():
    """
    Endpoint chính của API nén dữ liệu.
    """
    return {"message": "Compression API"}

@router.get("/devices")
def get_devices(db: Session = Depends(get_db)):
    """
    Lấy danh sách các thiết bị có dữ liệu nén.
    """
    try:
        # Lấy các thiết bị có dữ liệu nén
        devices = db.query(models.Device).filter(
            models.Device.compressed_data_optimized.any()
        ).all()
        
        result = []
        for device in devices:
            result.append({
                "device_id": device.device_id,
                "name": device.name,
                "description": device.description
            })
        
        return result
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thiết bị: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi database: {str(e)}")

@router.get("/compression-results/{device_id}")
def get_compression_results(device_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """
    Lấy kết quả nén dữ liệu của một thiết bị cụ thể.
    """
    try:
        # Kiểm tra thiết bị tồn tại
        device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy thiết bị với ID: {device_id}")
        
        # Lấy kết quả nén
        compression_results = db.query(models.CompressedDataOptimized).filter(
            models.CompressedDataOptimized.device_id == device_id
        ).order_by(models.CompressedDataOptimized.timestamp.desc()).limit(limit).all()
        
        result = []
        for cr in compression_results:
            result.append({
                "id": cr.id,
                "timestamp": cr.timestamp.isoformat() if cr.timestamp else None,
                "compression_ratio": cr.get_compression_ratio(),
                "time_range": cr.get_time_range_display()
            })
        
        return result
    except HTTPException as e:
        # Truyền lại HTTP exception
        raise e
    except Exception as e:
        logger.error(f"Lỗi khi lấy kết quả nén cho thiết bị {device_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi database: {str(e)}")

# TODO: Thêm các API endpoints khác cho việc nén và giải nén dữ liệu 