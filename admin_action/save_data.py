import subprocess
import os
import json
import logging
from sqlalchemy import create_engine, text
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5444'),
    'database': os.getenv('DB_NAME', 'iot_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '1234')
}

def setup_database():
    db_url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    engine = create_engine(db_url)
    return engine

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
    return [{"timestamp": t, "value": float(v)} for t, v in zip(timestamps, values)]

def decompress_device_data(device_id: str):
    engine = setup_database()
    record = get_latest_compression_by_device(engine, device_id)
    if not record:
        return None, "Không tìm thấy bản ghi nén phù hợp"
    meta = record['metadata']
    block_size = meta.get('block_size')
    num_buffers = meta.get('num_buffers')
    original_length = meta.get('original_length')
    encoded_stream = record['encoded_stream']
    time_range = record['time_range']
    decompressed_values = decompress_idealem(encoded_stream, block_size, num_buffers, original_length)
    # Lấy start_time, end_time từ time_range
    if hasattr(time_range, 'lower') and hasattr(time_range, 'upper'):
        start_time = time_range.lower.isoformat() if time_range.lower else None
        end_time = time_range.upper.isoformat() if time_range.upper else None
    elif isinstance(time_range, str) and time_range.startswith('[') and time_range.endswith(']'):
        start_time, end_time = time_range[1:-1].split(',')
        start_time = start_time.strip()
        end_time = end_time.strip()
    else:
        return None, f"Không xác định được time_range: {time_range}"
    timestamps = generate_timestamps(start_time, end_time, len(decompressed_values))
    data_with_time = combine_value_and_time(decompressed_values, timestamps)
    return data_with_time, None

def save_data(device_id: str):
    try:
        result = subprocess.run([
            "python3", "loss_compress.py", "--device-id", device_id
        ], capture_output=True, text=True, check=True)
        return {
            "success": True,
            "message": f"Đã chạy loss_compress.py cho device {device_id}",
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "message": f"Lỗi khi chạy loss_compress.py: {e}",
            "stdout": e.stdout,
            "stderr": e.stderr
        }
