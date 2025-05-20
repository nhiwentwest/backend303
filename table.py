#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tiện ích làm việc với các bảng dữ liệu trong hệ thống nén dữ liệu.
File này cung cấp các hàm để tạo, kiểm tra và quản lý các bảng dữ liệu.
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
import psycopg2
import json
import datetime
from typing import List, Dict, Any, Optional, Union

# Import các model từ models.py
from models import Base, Device, OriginalSample, CompressedData, CompressedDataOptimized

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("database.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Kết nối database từ biến môi trường
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "compression")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def create_engine_and_session():
    """
    Tạo engine và session để làm việc với SQLAlchemy ORM.
    
    Returns:
        tuple: (engine, session)
    """
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    return engine, session

def setup_database():
    """
    Thiết lập kết nối đến database và tạo các bảng nếu chưa tồn tại.
    
    Returns:
        engine: SQLAlchemy engine, hoặc None nếu không thể kết nối
    """
    try:
        # Tạo engine
        engine = create_engine(DATABASE_URL)
        
        # Tạo tất cả các bảng được định nghĩa trong models.py
        Base.metadata.create_all(bind=engine)
        logger.info(f"Đã kết nối thành công đến database và tạo các bảng: {DATABASE_URL}")
        
        # Kiểm tra kết nối và các bảng đã tạo
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = inspector.get_table_names()
            logger.info(f"Các bảng hiện có trong database: {', '.join(tables)}")
            
        return engine
    except Exception as e:
        logger.error(f"Lỗi khi thiết lập database: {str(e)}")
        return None

def check_table_exists(table_name: str) -> bool:
    """
    Kiểm tra xem bảng có tồn tại trong database không.
    
    Args:
        table_name: Tên bảng cần kiểm tra
        
    Returns:
        bool: True nếu bảng tồn tại, False nếu không
    """
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            inspector = inspect(conn)
            tables = inspector.get_table_names()
            return table_name in tables
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra bảng {table_name}: {str(e)}")
        return False

def ensure_device_exists(device_id: str, name: str = None, description: str = None) -> bool:
    """
    Đảm bảo thiết bị tồn tại trong bảng devices, nếu chưa thì tạo mới.
    
    Args:
        device_id: ID của thiết bị
        name: Tên thiết bị (tùy chọn)
        description: Mô tả thiết bị (tùy chọn)
        
    Returns:
        bool: True nếu thiết bị đã tồn tại hoặc đã được thêm thành công
    """
    try:
        engine, session = create_engine_and_session()
        
        # Kiểm tra xem thiết bị đã tồn tại chưa
        device = session.query(Device).filter(Device.device_id == device_id).first()
        
        if device:
            logger.info(f"Thiết bị {device_id} đã tồn tại trong hệ thống")
            return True
        
        # Nếu chưa tồn tại, tạo mới
        new_device = Device(
            device_id=device_id,
            name=name or f"Device {device_id}",
            description=description or f"Thiết bị được tự động thêm vào hệ thống"
        )
        
        session.add(new_device)
        session.commit()
        logger.info(f"Đã tạo thiết bị mới với device_id: {device_id}")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi đảm bảo thiết bị tồn tại: {str(e)}")
        session.rollback()
        return False
    finally:
        session.close()

def create_sample_data():
    """
    Tạo dữ liệu mẫu cho các bảng trong hệ thống.
    """
    try:
        engine, session = create_engine_and_session()
        
        # Tạo thiết bị mẫu nếu chưa tồn tại
        device_id = "sample_device"
        if not ensure_device_exists(device_id, "Sample Device", "Thiết bị mẫu cho demo"):
            raise Exception("Không thể tạo thiết bị mẫu")
        
        # Tạo dữ liệu mẫu cho bảng original_samples
        start_time = datetime.datetime.now()
        for i in range(10):
            # Tạo dữ liệu đa chiều
            original_data = {
                "power": 100 + i * 10,
                "humidity": 50 + i,
                "pressure": 1013 + i,
                "temperature": 25 + i * 0.5
            }
            
            # Tạo timestamp với khoảng cách 1 giờ
            timestamp = start_time + datetime.timedelta(hours=i)
            
            # Tạo bản ghi mới
            sample = OriginalSample(
                device_id=device_id,
                original_data=original_data,
                timestamp=timestamp
            )
            session.add(sample)
        
        # Lưu dữ liệu original_samples
        session.commit()
        logger.info(f"Đã tạo 10 bản ghi mẫu cho bảng original_samples")
        
        # Tạo dữ liệu mẫu cho bảng compressed_data_optimized
        # Template mẫu
        template = {
            "power": [100, 110, 120, 130, 140],
            "humidity": [50, 51, 52, 53, 54],
            "pressure": [1013, 1014, 1015, 1016, 1017],
            "temperature": [25, 25.5, 26, 26.5, 27]
        }
        
        # Encoded stream mẫu
        encoded_stream = [
            {"template_id": 1, "start_idx": 0, "length": 5}
        ]
        
        # Metadata nén
        compression_metadata = {
            "compression_ratio": 4.5,
            "hit_ratio": 0.8,
            "avg_cer": 0.05,
            "num_blocks": 1,
            "total_values": 5,
            "num_templates": 1,
            "compression_time": datetime.datetime.now().isoformat()
        }
        
        # Phạm vi thời gian
        time_range_str = f"[{start_time.isoformat()},{(start_time + datetime.timedelta(hours=9)).isoformat()}]"
        
        # Kết nối trực tiếp để sử dụng kiểu TSRANGE
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        try:
            query = """
            INSERT INTO compressed_data_optimized 
            (device_id, compression_metadata, templates, encoded_stream, time_range, timestamp)
            VALUES 
            (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s::tsrange, %s)
            RETURNING id
            """
            
            templates_json = json.dumps({"1": template})
            encoded_stream_json = json.dumps(encoded_stream)
            compression_metadata_json = json.dumps(compression_metadata)
            
            cursor.execute(query, (
                device_id,
                compression_metadata_json,
                templates_json,
                encoded_stream_json,
                time_range_str,
                datetime.datetime.now()
            ))
            
            compression_id = cursor.fetchone()[0]
            conn.commit()
            logger.info(f"Đã tạo dữ liệu nén mẫu với ID: {compression_id}")
        finally:
            cursor.close()
            conn.close()
        
        logger.info("Đã tạo dữ liệu mẫu thành công")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi tạo dữ liệu mẫu: {str(e)}")
        if 'session' in locals():
            session.rollback()
        return False

def get_original_samples(device_id: str = None, limit: int = 100) -> List[Dict]:
    """
    Lấy dữ liệu gốc từ bảng original_samples.
    
    Args:
        device_id: ID của thiết bị (tùy chọn)
        limit: Số lượng bản ghi tối đa
        
    Returns:
        List[Dict]: Danh sách các bản ghi dữ liệu
    """
    try:
        engine, session = create_engine_and_session()
        
        # Truy vấn dữ liệu
        query = session.query(OriginalSample)
        if device_id:
            query = query.filter(OriginalSample.device_id == device_id)
        query = query.order_by(OriginalSample.timestamp.desc()).limit(limit)
        
        # Chuyển đổi kết quả thành list dict
        results = []
        for sample in query.all():
            results.append({
                "id": sample.id,
                "device_id": sample.device_id,
                "original_data": sample.original_data,
                "timestamp": sample.timestamp.isoformat() if sample.timestamp else None
            })
            
        logger.info(f"Đã lấy {len(results)} bản ghi từ bảng original_samples")
        return results
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ original_samples: {str(e)}")
        return []
    finally:
        session.close()

def get_compressed_data(device_id: str = None, limit: int = 100) -> List[Dict]:
    """
    Lấy dữ liệu nén từ bảng compressed_data_optimized.
    
    Args:
        device_id: ID của thiết bị (tùy chọn)
        limit: Số lượng bản ghi tối đa
        
    Returns:
        List[Dict]: Danh sách các bản ghi dữ liệu nén
    """
    try:
        # Sử dụng truy vấn SQL trực tiếp vì TSRANGE không được hỗ trợ tốt trong SQLAlchemy
        engine = create_engine(DATABASE_URL)
        
        # Tạo câu truy vấn
        query = """
        SELECT id, device_id, timestamp, compression_metadata, time_range::text
        FROM compressed_data_optimized
        """
        
        params = {}
        if device_id:
            query += " WHERE device_id = :device_id"
            params['device_id'] = device_id
            
        query += " ORDER BY timestamp DESC LIMIT :limit"
        params['limit'] = limit
        
        # Thực hiện truy vấn
        results = []
        with engine.connect() as conn:
            rs = conn.execute(text(query), params)
            for row in rs:
                # Chuyển đổi JSONB thành dict
                metadata = row[3]
                # Chuyển đổi time_range từ text
                time_range = row[4]
                
                results.append({
                    "id": row[0],
                    "device_id": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "compression_metadata": metadata,
                    "time_range": time_range
                })
                
        logger.info(f"Đã lấy {len(results)} bản ghi từ bảng compressed_data_optimized")
        return results
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ compressed_data_optimized: {str(e)}")
        return []

def example_usage():
    """
    Hàm thể hiện ví dụ về cách sử dụng các bảng dữ liệu.
    """
    print("\n===== HƯỚNG DẪN SỬ DỤNG CÁC BẢNG DỮ LIỆU =====")
    print("\n1. Thiết lập database và tạo các bảng:")
    print("```python")
    print("from table import setup_database")
    print("engine = setup_database()")
    print("```")
    
    print("\n2. Đảm bảo thiết bị tồn tại:")
    print("```python")
    print("from table import ensure_device_exists")
    print("ensure_device_exists('my_device', 'My Device Name', 'My Device Description')")
    print("```")
    
    print("\n3. Tạo dữ liệu mẫu:")
    print("```python")
    print("from table import create_sample_data")
    print("create_sample_data()")
    print("```")
    
    print("\n4. Lấy dữ liệu gốc:")
    print("```python")
    print("from table import get_original_samples")
    print("samples = get_original_samples(device_id='my_device', limit=100)")
    print("for sample in samples:")
    print("    print(f\"ID: {sample['id']}, Timestamp: {sample['timestamp']}\")")
    print("    print(f\"Data: {sample['original_data']}\")")
    print("```")
    
    print("\n5. Lấy dữ liệu nén:")
    print("```python")
    print("from table import get_compressed_data")
    print("compressed = get_compressed_data(device_id='my_device', limit=100)")
    print("for data in compressed:")
    print("    print(f\"ID: {data['id']}, Timestamp: {data['timestamp']}\")")
    print("    print(f\"Compression Ratio: {data['compression_metadata'].get('compression_ratio')}\")")
    print("    print(f\"Time Range: {data['time_range']}\")")
    print("```")
    
    print("\n6. Sử dụng các model SQLAlchemy:")
    print("```python")
    print("from sqlalchemy.orm import sessionmaker")
    print("from sqlalchemy import create_engine")
    print("from models import Device, OriginalSample, CompressedDataOptimized")
    print()
    print("# Tạo session")
    print("engine = create_engine('postgresql://postgres:1234@localhost:5444/iot_db')")
    print("Session = sessionmaker(bind=engine)")
    print("session = Session()")
    print()
    print("# Truy vấn thiết bị")
    print("devices = session.query(Device).all()")
    print("for device in devices:")
    print("    print(f\"Device ID: {device.device_id}, Name: {device.name}\")")
    print()
    print("# Đóng session")
    print("session.close()")
    print("```")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        # Thiết lập database
        engine = setup_database()
        if engine:
            print("Đã thiết lập database thành công")
            
            # Tạo dữ liệu mẫu nếu có tham số --sample-data
            if len(sys.argv) > 2 and sys.argv[2] == "--sample-data":
                if create_sample_data():
                    print("Đã tạo dữ liệu mẫu thành công")
                else:
                    print("Không thể tạo dữ liệu mẫu")
    else:
        # Hiển thị hướng dẫn sử dụng
        print("Tiện ích làm việc với các bảng dữ liệu trong hệ thống nén dữ liệu")
        print("\nCách sử dụng:")
        print("  python table.py --setup              # Thiết lập database và tạo các bảng")
        print("  python table.py --setup --sample-data # Thiết lập database và tạo dữ liệu mẫu")
        print("  python table.py                      # Hiển thị hướng dẫn sử dụng\n")
        
        # Hiển thị ví dụ về cách sử dụng
        example_usage() 