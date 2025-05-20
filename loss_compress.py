#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script nén dữ liệu lossless từ bảng original_samples, lưu kết quả vào bảng compressed_data_optimized.
Sử dụng thuật toán nén lossless từ module lossless_compression.py.
"""


import json
import sys
import os
import logging
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine, text, inspect
import pandas as pd
import argparse
import matplotlib.pyplot as plt
import numpy as np
import psycopg2
from dotenv import load_dotenv
import traceback

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import thuật toán nén lossless
from lossless_compression import LosslessCompressor

# Import từ module visualization_analyzer
from visualization_analyzer import create_visualizations

# Cấu hình database
load_dotenv()
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5444'),
    'database': os.getenv('DB_NAME', 'iot_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234')
}

# Lớp JSONEncoder tùy chỉnh cho việc chuyển đổi các kiểu dữ liệu NumPy và boolean
class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return obj
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, bool):
            return bool(obj)
        return super().default(obj)

def convert_date_keys_to_str(obj):
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if isinstance(k, (date, datetime)):
                k = k.isoformat()
            new_dict[k] = convert_date_keys_to_str(v)
        return new_dict
    elif isinstance(obj, list):
        return [convert_date_keys_to_str(i) for i in obj]
    else:
        return obj

def setup_optimized_database():
    """Thiết lập kết nối database và tạo bảng nếu chưa tồn tại"""
    # Tạo URL kết nối database
    db_url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    
    try:
        engine = create_engine(db_url)
        
        # Kiểm tra kết nối
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            
        # Kiểm tra và tạo bảng nếu chưa tồn tại
        inspector = inspect(engine)
        if "compressed_data_optimized" not in inspector.get_table_names():
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE compressed_data_optimized (
                        id SERIAL PRIMARY KEY,
                        device_id VARCHAR(255) NOT NULL,
                        compression_metadata JSONB,
                        encoded_stream JSONB,
                        time_range TSRANGE,
                        FOREIGN KEY (device_id) REFERENCES devices(device_id)
                    );
                    CREATE INDEX idx_compressed_data_optimized_device_id ON compressed_data_optimized(device_id);
                    CREATE INDEX idx_compressed_data_optimized_time_range ON compressed_data_optimized USING GIST(time_range);
                """))
                conn.commit()
                
        return engine
        
    except Exception as e:
        logging.error(f"Database connection error: {str(e)}")
        raise

def ensure_device_exists(engine, device_id):
    """Đảm bảo device_id tồn tại trong bảng devices"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM devices WHERE device_id = :device_id"),
            {"device_id": device_id}
        ).scalar()
        
        if result == 0:
            raise ValueError(f"Device {device_id} not found in database")

def fetch_original_data(engine, device_id=None):
    """
    Lấy toàn bộ dữ liệu gốc của device từ bảng original_samples
    """
    query = """
        SELECT value, timestamp 
        FROM original_samples 
        WHERE 1=1
    """
    params = {}
    if device_id:
        query += " AND device_id = :device_id"
        params["device_id"] = device_id
    query += " ORDER BY timestamp ASC"
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)
    if df.empty:
        raise ValueError("No data found")
    timestamps = df['timestamp'].tolist()
    data = df['value'].values
    return data, timestamps

def save_optimized_compression_result(engine, device_id, compression_result, timestamps=None):
    """
    Lưu kết quả nén vào bảng compressed_data_optimized
    """
    if not timestamps:
        timestamps = [datetime.now()]
    time_range = f"[{min(timestamps)}, {max(timestamps)}]"

    # Chỉ lấy các trường thực sự có trong kết quả nén mới
    compression_metadata = {
        'hit_ratio': compression_result.get('hit_ratio'),
        'compression_ratio': compression_result.get('compression_ratio'),
        'block_size': compression_result.get('block_size'),
        'num_buffers': compression_result.get('num_buffers'),
        'original_length': compression_result.get('original_length')
    }

    data = {
        "device_id": device_id,
        "compression_metadata": json.dumps(compression_metadata, cls=MyEncoder),
        "encoded_stream": json.dumps(compression_result['encoded_stream'], cls=MyEncoder),
        "time_range": time_range
    }

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO compressed_data_optimized 
                (device_id, compression_metadata, encoded_stream, time_range)
                VALUES 
                (:device_id, :compression_metadata, :encoded_stream, :time_range)
                RETURNING id
            """),
            data
        )
        compression_id = result.scalar()
        conn.commit()

    # --- TÍNH COMPRESSION RATIO THỰC TẾ VÀ UPDATE THEO DEVICE_ID ---
    with engine.connect() as conn:
        # Lấy kích thước dữ liệu gốc (tổng số byte)
        original_size = conn.execute(
            text("""
                SELECT SUM(pg_column_size(value)) 
                FROM original_samples 
                WHERE device_id = :device_id
            """),
            {"device_id": device_id}
        ).scalar() or 0

        # Lấy kích thước dữ liệu nén (tổng số byte của encoded_stream)
        compressed_size = conn.execute(
            text("""
                SELECT pg_column_size(encoded_stream)
                FROM compressed_data_optimized
                WHERE device_id = :device_id
                ORDER BY id DESC LIMIT 1
            """),
            {"device_id": device_id}
        ).scalar() or 0

        # Tính compression ratio
        compression_ratio = (original_size / compressed_size) if compressed_size > 0 else 0

        # Lấy metadata hiện tại
        compression_metadata = conn.execute(
            text("""
                SELECT compression_metadata
                FROM compressed_data_optimized
                WHERE device_id = :device_id
                ORDER BY id DESC LIMIT 1
            """),
            {"device_id": device_id}
        ).scalar()

        # Update compression_ratio vào metadata (JSON)
        if isinstance(compression_metadata, str):
            meta = json.loads(compression_metadata)
        else:
            meta = compression_metadata
        meta['compression_ratio'] = compression_ratio

        conn.execute(
            text("""
                UPDATE compressed_data_optimized
                SET compression_metadata = :new_meta
                WHERE id = (
                    SELECT id FROM compressed_data_optimized
                    WHERE device_id = :device_id
                    ORDER BY id DESC LIMIT 1
                )
            """),
            {"new_meta": json.dumps(meta), "device_id": device_id}
        )
        conn.commit()
        logger.info(f"Updated compression_ratio={compression_ratio:.4f} for device_id={device_id}")

    return compression_id

def run_compression(device_id=None, limit=200000, output_file=None, 
                   visualize=False, output_dir=None, visualize_max_points=5000, 
                   visualize_sampling='adaptive', visualize_chunks=0):
    try:
        engine = setup_optimized_database()
        if device_id:
            ensure_device_exists(engine, device_id)
        data, timestamps = fetch_original_data(engine, device_id=device_id)
        print("Data length:", len(data))
        logger.info(f"Data length: {len(data)}")
        if len(data) == 0:
            raise ValueError("No data to compress")
        compressor = LosslessCompressor()
        print("Block size:", compressor.block_size)
        logger.info(f"Block size: {compressor.block_size}")
        compression_result = compressor.compress(data)
        compression_id = save_optimized_compression_result(
            engine, 
            device_id, 
            compression_result,
            timestamps
        )
        logger.info(f"Compression completed. Compression ID: {compression_id}")
        if visualize:
            if not output_dir:
                output_dir = f"visualization_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            create_visualizations(
                data=data,
                compression_result=compression_result,
                output_dir=output_dir,
                max_points=visualize_max_points,
                sampling_method=visualize_sampling,
                num_chunks=visualize_chunks,
                compression_id=compression_id,
                device_id=device_id
            )
            logger.info(f"Visualizations saved to {output_dir}")
        return compression_id
    except Exception as e:
        logger.error(f"Error during compression: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def main():
    parser = argparse.ArgumentParser(description='Lossless compression of sensor data')
    parser.add_argument('--device-id', type=str, help='Device ID to compress')
    parser.add_argument('--limit', type=int, default=200000, help='Maximum number of samples')
    parser.add_argument('--output', type=str, help='Output file for compression results')
    parser.add_argument('--visualize', action='store_true', help='Create visualizations')
    parser.add_argument('--output-dir', type=str, help='Directory for visualizations')
    parser.add_argument('--max-points', type=int, default=5000, help='Maximum points in visualization')
    parser.add_argument('--sampling', type=str, default='adaptive', choices=['adaptive', 'uniform'],
                      help='Sampling method for visualization')
    parser.add_argument('--chunks', type=int, default=0, help='Number of chunks for visualization')
    args = parser.parse_args()
    run_compression(
        device_id=args.device_id,
        limit=args.limit,
        output_file=args.output,
        visualize=args.visualize,
        output_dir=args.output_dir,
        visualize_max_points=args.max_points,
        visualize_sampling=args.sampling,
        visualize_chunks=args.chunks
    )

if __name__ == "__main__":
    main() 