#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Models cho các bảng dữ liệu trong hệ thống.
Các lớp này định nghĩa cấu trúc dữ liệu cho SQLAlchemy ORM.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, Boolean, Text, Numeric, UniqueConstraint, CheckConstraint, ForeignKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, TSRANGE
import datetime

Base = declarative_base()

class User(Base):
    """
    Bảng chứa thông tin người dùng hệ thống.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    role = Column(String, default="user")
    
    # Relationships
    devices = relationship("Device", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

class Device(Base):
    """
    Bảng chứa thông tin về các thiết bị IoT trong hệ thống.
    """
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "device_type IN ('yolo-device', 'yolo-fan', 'yolo-light')",
            name="device_type_check"
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    device_type = Column(String(32), default="yolo-device")
    
    # Relationships
    user = relationship("User", back_populates="devices")
    original_samples = relationship("OriginalSamples", back_populates="device")
    compressed_data_optimized = relationship("CompressedDataOptimized", back_populates="device")
    sensor_data = relationship("SensorData", back_populates="device")
    feeds = relationship("Feed", back_populates="device", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Device(id={self.id}, device_id='{self.device_id}')>"

class OriginalSamples(Base):
    """
    Bảng chứa dữ liệu gốc từ thiết bị.
    """
    __tablename__ = "original_samples"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    value = Column(Numeric(10,2), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationship với Device
    device = relationship("Device", back_populates="original_samples")
    
    def __repr__(self):
        return f"<OriginalSamples(id={self.id}, device_id='{self.device_id}')>"

class SensorData(Base):
    """
    Bảng chứa dữ liệu cảm biến từ các thiết bị.
    """
    __tablename__ = "sensor_data"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    feed_id = Column(String, index=True, nullable=False)
    value = Column(Float)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    # Relationships
    device = relationship("Device", back_populates="sensor_data")
    feed = relationship("Feed", back_populates="sensor_data")
    __table_args__ = (
        UniqueConstraint('device_id', 'feed_id', name='uix_device_feed_sensor_data'),
        ForeignKeyConstraint(
            ['device_id', 'feed_id'],
            ['feeds.device_id', 'feeds.feed_id'],
            ondelete='CASCADE',
            name='sensor_data_device_feed_fkey'
        ),
    )
    def __repr__(self):
        return f"<SensorData(id={self.id}, device_id='{self.device_id}', feed_id='{self.feed_id}', value={self.value})>"

class CompressedDataOptimized(Base):
    """
    Bảng chứa dữ liệu nén theo cấu trúc tối ưu mới.
    Mỗi bản ghi chứa đầy đủ thông tin về quá trình nén, bao gồm:
    - compression_metadata: Metadata của quá trình nén (tỷ lệ nén, hit ratio, v.v.)
    - encoded_stream: Chuỗi mã hóa chứa thông tin về cách sử dụng các template
    - time_range: Phạm vi thời gian của dữ liệu được nén
    """
    __tablename__ = "compressed_data_optimized"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    compression_metadata = Column(JSONB, comment="Lưu thông tin nén (compression_ratio, hit_ratio, etc)")
    encoded_stream = Column(JSONB, comment="Lưu chuỗi mã hóa")
    time_range = Column(TSRANGE, comment="Phạm vi thời gian của dữ liệu", index=True)
    
    # Relationship
    device = relationship("Device", back_populates="compressed_data_optimized")
    
    def __repr__(self):
        return f"<CompressedDataOptimized(id={self.id}, device_id='{self.device_id}')>"

    def get_compression_ratio(self):
        """Trả về tỷ lệ nén từ metadata"""
        if self.compression_metadata and 'compression_ratio' in self.compression_metadata:
            return self.compression_metadata['compression_ratio']
        return 0
    
    def get_time_range_display(self):
        """Trả về phạm vi thời gian dưới dạng hiển thị"""
        if self.time_range:
            try:
                if hasattr(self.time_range, 'lower') and hasattr(self.time_range, 'upper'):
                    lower = self.time_range.lower.isoformat() if self.time_range.lower else "N/A"
                    upper = self.time_range.upper.isoformat() if self.time_range.upper else "N/A"
                    return f"{lower} đến {upper}"
            except:
                pass
        return "Không có thông tin thời gian"

class Feed(Base):
    """
    Bảng mapping giữa feed_id của Adafruit IO và device_id trong hệ thống
    """
    __tablename__ = "feeds"
    
    feed_id = Column(String, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"), primary_key=True, index=True)
    
    # Relationships
    device = relationship("Device", back_populates="feeds")
    sensor_data = relationship("SensorData", back_populates="feed", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Feed(feed_id='{self.feed_id}', device_id='{self.device_id}')>"
