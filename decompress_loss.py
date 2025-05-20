#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script giải nén dữ liệu lossless từ bảng compressed_data_optimized.
Sử dụng thuật toán giải nén lossless từ module lossless_compression.py.
"""

import sys
import os
import json
import logging
from sqlalchemy import create_engine, text
import numpy as np
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Cấu hình logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cấu hình database
load_dotenv()
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5444'),
    'database': os.getenv('DB_NAME', 'iot_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234')
}

def setup_database():
    """Thiết lập kết nối database"""
    try:
        db_url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

def get_latest_compression_by_device(engine, device_id):
    query = """
    SELECT id, device_id, compression_metadata, encoded_stream, time_range
    FROM compressed_data_optimized
    WHERE device_id = :device_id
    ORDER BY id DESC
    LIMIT 1
    """
    with engine.connect() as conn:
        result = conn.execute(text(query), {"device_id": device_id})
        row = result.fetchone()
        if not row:
            logger.error(f"Không tìm thấy bản ghi nén cho device_id: {device_id}")
            return None
        metadata = row[2]
        encoded_stream = row[3]
        time_range = row[4]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if isinstance(encoded_stream, str):
            encoded_stream = json.loads(encoded_stream)
        return {
            'id': row[0],
            'device_id': row[1],
            'metadata': metadata,
            'encoded_stream': encoded_stream,
            'time_range': time_range
        }

def decompress_idealem(encoded_stream, block_size, num_buffers, original_length):
    buffers = []
    data = []
    i = 0
    while i < len(encoded_stream):
        code = encoded_stream[i]
        if isinstance(code, (int, np.integer)) and code == 0xFE:
            i += 1
            block_size = encoded_stream[i]
            buffers = []
        elif isinstance(code, (int, np.integer)) and code == 0xFF:
            i += 1
            overwrite_idx = encoded_stream[i]
            i += 1
            block = encoded_stream[i]
            if isinstance(block, np.ndarray):
                block = block.tolist()
            while len(buffers) <= overwrite_idx:
                buffers.append([0]*block_size)
            buffers[overwrite_idx] = block.copy() if isinstance(block, list) else [block]
            if isinstance(block, list):
                data.extend(block)
            else:
                data.append(block)
        elif isinstance(code, (int, np.integer)) and code == 0xFD:
            i += 1
            block = encoded_stream[i]
            if isinstance(block, np.ndarray):
                block = block.tolist()
            if len(buffers) < num_buffers:
                buffers.append(block.copy() if isinstance(block, list) else [block])
            else:
                buffers[0] = block.copy() if isinstance(block, list) else [block]
            if isinstance(block, list):
                data.extend(block)
            else:
                data.append(block)
        elif isinstance(code, (int, np.integer)) and code < num_buffers:
            block = buffers[code]
            if isinstance(block, list):
                data.extend(block)
            else:
                data.append(block)
        i += 1
    return np.array(data[:original_length])

def generate_timestamps(start_time, end_time, n):
    start = datetime.fromisoformat(start_time)
    end = datetime.fromisoformat(end_time)
    if n == 1:
        return [start.isoformat()]
    delta = (end - start) / (n - 1)
    return [(start + i * delta).isoformat() for i in range(n)]

def combine_value_and_time(values, timestamps):
    return [{"timestamp": t, "value": v} for t, v in zip(timestamps, values)]

def save_decompressed_data(data, output_file):
    """
    Lưu kết quả giải nén vào file
    
    Args:
        data: Dữ liệu giải nén
        output_file: Đường dẫn file đầu ra
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    try:
        if not data:
            logger.warning("Không có dữ liệu giải nén để lưu")
            return False
            
        # Đảm bảo thư mục đầu ra tồn tại
        output_dir = os.path.dirname(os.path.abspath(output_file))
        os.makedirs(output_dir, exist_ok=True)
        
        # Lưu vào file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        # Hiển thị thông tin file
        file_size = os.path.getsize(output_file) / 1024  # Kích thước theo KB
        logger.info(f"Đã lưu kết quả giải nén vào file: {output_file} ({file_size:.2f} KB)")
        
        return True
    except Exception as e:
        logger.error(f"Lỗi khi lưu kết quả giải nén: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Giải nén dữ liệu lossless IDEALEM')
    parser.add_argument('--device-id', type=str, required=True, help='ID của thiết bị')
    args = parser.parse_args()

    engine = setup_database()
    record = get_latest_compression_by_device(engine, args.device_id)
    if not record:
        logger.error("Không tìm thấy bản ghi nén phù hợp")
        return

    meta = record['metadata']
    block_size = meta.get('block_size')
    num_buffers = meta.get('num_buffers')
    original_length = meta.get('original_length')
    encoded_stream = record['encoded_stream']
    time_range = record['time_range']

    logger.info(f"Giải nén với block_size={block_size}, num_buffers={num_buffers}, original_length={original_length}")

    decompressed_values = decompress_idealem(encoded_stream, block_size, num_buffers, original_length)

    # Lấy start_time, end_time từ time_range (hỗ trợ cả tsrange object và string)
    if hasattr(time_range, 'lower') and hasattr(time_range, 'upper'):
        start_time = time_range.lower.isoformat() if time_range.lower else None
        end_time = time_range.upper.isoformat() if time_range.upper else None
    elif isinstance(time_range, str) and time_range.startswith('[') and time_range.endswith(']'):
        start_time, end_time = time_range[1:-1].split(',')
        start_time = start_time.strip()
        end_time = end_time.strip()
    else:
        logger.error(f"Không xác định được time_range: {time_range}")
        return

    timestamps = generate_timestamps(start_time, end_time, len(decompressed_values))
    data_with_time = combine_value_and_time(decompressed_values, timestamps)
    output_file = f"{args.device_id}.json"
    save_decompressed_data(data_with_time, output_file)
    logger.info(f"Giải nén hoàn tất! Đã lưu vào {output_file}")

if __name__ == "__main__":
    main() 