#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script giải nén dữ liệu từ bảng compressed_data_optimized và lưu kết quả vào file JSON.
Cách tiếp cận tối ưu không sử dụng bảng ref.
"""

import sys
import os
import json
import logging
import argparse
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Result

# Import lớp MyEncoder từ compress.py
try:
    from compress import MyEncoder
except ImportError:
    # Định nghĩa MyEncoder nếu không thể import
    class MyEncoder(json.JSONEncoder):
        """
        Custom JSON encoder để xử lý kiểu dữ liệu không chuẩn như NumPy arrays
        """
        def default(self, obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            elif np.isnan(obj) or np.isinf(obj):
                return None
            elif hasattr(obj, 'lower') and hasattr(obj, 'upper'):  # Xử lý kiểu DateTimeRange của PostgreSQL
                try:
                    # Nếu là tsrange hoặc kiểu tương tự, chuyển thành chuỗi
                    return str(obj)
                except:
                    return f"[{obj.lower},{obj.upper}]" if hasattr(obj, 'lower') and hasattr(obj, 'upper') else str(obj)
            return super(MyEncoder, self).default(obj)

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("decompress.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Kết nối database từ biến môi trường
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5433/iot_db")

def setup_database():
    """
    Thiết lập kết nối với database và kiểm tra cấu trúc bảng
    
    Returns:
        engine: SQLAlchemy engine
    """
    try:
        # Kết nối đến database
        engine = create_engine(DATABASE_URL)
        
        # Kiểm tra kết nối
        with engine.connect() as conn:
            # Kiểm tra các bảng đã tồn tại
            inspector = inspect(conn)
            tables = inspector.get_table_names()
            
            # Kiểm tra bảng compressed_data_optimized
            if 'compressed_data_optimized' not in tables:
                logger.error("Bảng compressed_data_optimized không tồn tại trong database")
                raise ValueError("Bảng compressed_data_optimized không tồn tại")
                    
            logger.info(f"Đã kết nối thành công đến database: {DATABASE_URL}")
            return engine
    except Exception as e:
        logger.error(f"Lỗi khi kết nối đến database: {str(e)}")
        raise

def get_compression_record(engine, compression_id):
    """
    Lấy dữ liệu nén từ bảng compressed_data_optimized
    
    Args:
        engine: SQLAlchemy engine
        compression_id: ID của bản ghi nén
        
    Returns:
        dict: Dữ liệu nén hoặc None nếu không tìm thấy
    """
    try:
        query = """
        SELECT id, device_id, compression_metadata, encoded_stream, time_range
        FROM compressed_data_optimized
        WHERE id = :compression_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {"compression_id": compression_id})
            row = result.fetchone()
            
            if not row:
                logger.warning(f"Không tìm thấy bản ghi nén với ID: {compression_id}")
                return None
            
            # Xử lý các trường JSON
            metadata = row[3]
            encoded_stream = row[4]
            
            # Chỉ chuyển đổi từ JSON nếu là chuỗi
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            if isinstance(encoded_stream, str):
                encoded_stream = json.loads(encoded_stream)
            
            # Xử lý mảng NumPy trong metadata nếu có
            if isinstance(metadata, dict):
                for key, value in list(metadata.items()):
                    if isinstance(value, np.ndarray):
                        metadata[key] = value.tolist()
            
            # Xử lý mảng NumPy trong encoded_stream nếu có
            if isinstance(encoded_stream, list):
                for block in encoded_stream:
                    if isinstance(block, dict):
                        for key, value in list(block.items()):
                            if isinstance(value, np.ndarray):
                                block[key] = value.tolist()
                
            # Chuyển đổi dữ liệu từ JSON
            compression_record = {
                'id': row[0],
                'device_id': row[1],
                'metadata': metadata,
                'encoded_stream': encoded_stream,
                'time_range': row[5]
            }
            
            return compression_record
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu nén: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def find_compression_by_device_id(conn, device_id, limit=10):
    query = """
        SELECT id, device_id, compression_metadata, encoded_stream, time_range
        FROM compressed_data_optimized
        WHERE device_id = :device_id
        ORDER BY id DESC
        LIMIT :limit
    """
    result = conn.execute(text(query), {"device_id": device_id, "limit": limit})
    return result.fetchall()

def find_compression_by_time_range(engine, start_time, end_time, device_id=None, limit=10):
    """
    Tìm các bản ghi nén theo khoảng thời gian
    
    Args:
        engine: SQLAlchemy engine
        start_time: Thời gian bắt đầu (định dạng YYYY-MM-DD)
        end_time: Thời gian kết thúc (định dạng YYYY-MM-DD)
        device_id: ID của thiết bị (tùy chọn)
        limit: Số lượng bản ghi tối đa cần lấy
        
    Returns:
        list: Danh sách các bản ghi nén
    """
    try:
        # Chuẩn bị truy vấn
        query = """
        SELECT id, device_id, compression_metadata, encoded_stream, time_range
        FROM compressed_data_optimized
        WHERE time_range && :time_range
        """
        
        params = {
            "time_range": f"[{start_time}, {end_time}]"
        }
        
        # Thêm điều kiện device_id nếu có
        if device_id:
            query += " AND device_id = :device_id"
            params["device_id"] = device_id
            
        # Thêm sắp xếp và giới hạn
        query += " ORDER BY id DESC LIMIT :limit"
        params["limit"] = limit
        
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            records = []
            
            for row in result:
                # Xử lý các trường JSON
                metadata = row[3]
                encoded_stream = row[4]
                
                # Chỉ chuyển đổi từ JSON nếu là chuỗi
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                if isinstance(encoded_stream, str):
                    encoded_stream = json.loads(encoded_stream)
                
                # Xử lý mảng NumPy trong metadata nếu có
                if isinstance(metadata, dict):
                    for key, value in list(metadata.items()):
                        if isinstance(value, np.ndarray):
                            metadata[key] = value.tolist()
                
                # Xử lý mảng NumPy trong encoded_stream nếu có
                if isinstance(encoded_stream, list):
                    for block in encoded_stream:
                        if isinstance(block, dict):
                            for key, value in list(block.items()):
                                if isinstance(value, np.ndarray):
                                    block[key] = value.tolist()
                
                # Chuyển đổi dữ liệu từ JSON
                compression_record = {
                    'id': row[0],
                    'device_id': row[1],
                    'metadata': metadata,
                    'encoded_stream': encoded_stream,
                    'time_range': row[5]
                }
                
                records.append(compression_record)
                
            return records
    except Exception as e:
        logger.error(f"Lỗi khi tìm bản ghi nén theo khoảng thời gian: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def decompress_data(compression_record):
    """
    Giải nén dữ liệu từ bản ghi nén
    
    Args:
        compression_record: Dict chứa dữ liệu nén từ bảng compressed_data_optimized
        
    Returns:
        dict: Kết quả giải nén hoặc None nếu có lỗi
    """
    try:
        # Khởi tạo kết quả
        decompressed_results = {
            'device_id': compression_record.get('device_id'),
            'metadata': {},
            'decompressed_data': []
        }

        # Lấy các thành phần cần thiết
        encoded_stream = compression_record.get('encoded_stream', [])
        time_range = compression_record.get('time_range')
        
        # Lấy metadata từ bản ghi nén
        compression_metadata = compression_record.get('metadata', {})
        
        # Sao chép các thông tin từ metadata của bản ghi nén
        if compression_metadata:
            decompressed_results['metadata']['total_values'] = compression_metadata.get('total_values', 0)
            decompressed_results['metadata']['num_templates'] = compression_metadata.get('num_templates', 0)
            decompressed_results['metadata']['compression_ratio'] = compression_metadata.get('compression_ratio', 0)
        
        # Xử lý time_range
        if time_range:
            try:
                if hasattr(time_range, 'lower') and hasattr(time_range, 'upper'):
                    lower = time_range.lower.isoformat() if time_range.lower else None
                    upper = time_range.upper.isoformat() if time_range.upper else None
                    decompressed_results['metadata']['time_range'] = f"[{lower},{upper}]"
                    first_timestamp = lower
                    last_timestamp = upper
                else:
                    decompressed_results['metadata']['time_range'] = str(time_range)
                    # Trích xuất thời gian từ chuỗi
                    time_str = str(time_range)
                    if time_str.startswith('[') and time_str.endswith(']'):
                        time_parts = time_str[1:-1].split(',')
                        if len(time_parts) == 2:
                            first_timestamp = time_parts[0]
                            last_timestamp = time_parts[1]
            except Exception as e:
                logger.warning(f"Không thể xử lý time_range: {str(e)}")
                first_timestamp = last_timestamp = None

        # Phân phối thời gian cho các block nếu cần
        time_distribution = None
        if first_timestamp and last_timestamp and len(encoded_stream) > 1:
            try:
                time_distribution = generate_time_distribution(
                    first_timestamp,
                    last_timestamp,
                    len(encoded_stream)
                )
            except Exception as e:
                logger.warning(f"Không thể phân phối thời gian: {str(e)}")

        # Duyệt qua các block trong encoded_stream
        for i, block in enumerate(encoded_stream):
            template_id = str(block['template_id'])
            
            # Kiểm tra template tồn tại
            if template_id not in templates:
                logger.warning(f"Không tìm thấy template ID: {template_id}")
                continue
                
            # Lấy dữ liệu template
            template_data = templates[template_id]
            if isinstance(template_data, np.ndarray):
                template_data = template_data.tolist()
            
            # Tạo block giải nén
            decompressed_block = {
                'template_id': template_id,
                'values': template_data
            }
            
            # Thêm thông tin thời gian
            if time_distribution:
                decompressed_block['start_time'] = time_distribution[i]['start']
                decompressed_block['end_time'] = time_distribution[i]['end']
            
            decompressed_results['decompressed_data'].append(decompressed_block)

        # Sắp xếp kết quả theo thời gian nếu có
        if any('start_time' in block for block in decompressed_results['decompressed_data']):
            decompressed_results['decompressed_data'].sort(
                key=lambda x: x.get('start_time', '9999-12-31T23:59:59')
            )
        
        # Nếu không có thông tin trong metadata, tính toán từ dữ liệu giải nén
        if decompressed_results['metadata'].get('total_values', 0) == 0:
            total_values = 0
            for block in decompressed_results['decompressed_data']:
                values = block.get('values', [])
                if isinstance(values, list):
                    total_values += len(values)
                elif isinstance(values, dict):
                    for key, data_values in values.items():
                        if isinstance(data_values, list):
                            total_values += len(data_values)
            
            decompressed_results['metadata']['total_values'] = total_values
        
        # Nếu không có thông tin về số lượng template, tính toán từ dữ liệu giải nén
        if decompressed_results['metadata'].get('num_templates', 0) == 0:
            decompressed_results['metadata']['num_templates'] = len(templates)
        
        return decompressed_results

    except Exception as e:
        logger.error(f"Lỗi khi giải nén dữ liệu: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def generate_time_distribution(start_time_str, end_time_str, num_blocks):
    """
    Tạo phân phối thời gian cho các block dựa trên khoảng thời gian
    
    Args:
        start_time_str: Thời gian bắt đầu (định dạng ISO string)
        end_time_str: Thời gian kết thúc (định dạng ISO string)
        num_blocks: Số lượng block cần phân phối
        
    Returns:
        list: Danh sách các điểm thời gian theo dạng {start: time1, end: time2}
    """
    from datetime import datetime, timedelta
    from dateutil import parser
    
    # Chuyển đổi chuỗi thành đối tượng datetime
    try:
        # Làm sạch chuỗi thời gian nếu cần
        if start_time_str.startswith('"') and start_time_str.endswith('"'):
            start_time_str = start_time_str[1:-1]
        if end_time_str.startswith('"') and end_time_str.endswith('"'):
            end_time_str = end_time_str[1:-1]
            
        start_time = parser.parse(start_time_str)
        end_time = parser.parse(end_time_str)
    except Exception as e:
        logger.error(f"Lỗi khi phân tích thời gian: {str(e)}")
        raise
    
    # Tính toán khoảng thời gian
    total_seconds = (end_time - start_time).total_seconds()
    block_seconds = total_seconds / num_blocks if num_blocks > 0 else 0
    
    # Tạo danh sách điểm thời gian
    time_points = []
    for i in range(num_blocks):
        block_start = start_time + timedelta(seconds=i * block_seconds)
        block_end = start_time + timedelta(seconds=(i + 1) * block_seconds)
        
        # Đảm bảo block cuối cùng kết thúc đúng thời điểm end_time
        if i == num_blocks - 1:
            block_end = end_time
            
        time_points.append({
            'start': block_start.isoformat(),
            'end': block_end.isoformat()
        })
    
    return time_points

def save_decompressed_data(decompressed_results, output_file):
    """
    Lưu kết quả giải nén vào file
    
    Args:
        decompressed_results: Kết quả giải nén
        output_file: Đường dẫn file đầu ra
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    try:
        if not decompressed_results:
            logger.warning("Không có dữ liệu giải nén để lưu")
            return False
            
        # Đảm bảo thư mục đầu ra tồn tại
        output_dir = os.path.dirname(os.path.abspath(output_file))
        os.makedirs(output_dir, exist_ok=True)
        
        # Lưu vào file sử dụng MyEncoder để xử lý đúng đối tượng NumPy
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(decompressed_results, f, indent=2, cls=MyEncoder)
            
        # Hiển thị thông tin file
        file_size = os.path.getsize(output_file) / 1024  # Kích thước theo KB
        logger.info(f"Đã lưu kết quả giải nén vào file: {output_file} ({file_size:.2f} KB)")
        
        return True
    except Exception as e:
        logger.error(f"Lỗi khi lưu kết quả giải nén: {str(e)}")
        return False

def main():
    """
    Hàm chính để thực thi script
    """
    parser = argparse.ArgumentParser(description='Giải nén dữ liệu từ bảng compressed_data_optimized')
    parser.add_argument('--compression-id', type=int, help='ID của bản ghi nén cụ thể')
    parser.add_argument('--device-id', type=str, help='ID của thiết bị cần giải nén dữ liệu')
    parser.add_argument('--start-date', type=str, help='Ngày bắt đầu để lọc dữ liệu (định dạng YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='Ngày kết thúc để lọc dữ liệu (định dạng YYYY-MM-DD)')
    parser.add_argument('--output', type=str, help='Đường dẫn file đầu ra để lưu kết quả giải nén (nếu không cung cấp, kết quả sẽ được lưu theo tên thiết bị)')
    parser.add_argument('--limit', type=int, default=10, 
                        help='Số lượng bản ghi tối đa cần giải nén (mặc định: 10)')
    parser.add_argument('--list', action='store_true', help='Chỉ liệt kê các bản ghi nén, không giải nén')
    parser.add_argument('--show-time', action='store_true', help='Hiển thị thông tin thời gian chi tiết của các block dữ liệu')
    parser.add_argument('--console-only', action='store_true', help='Chỉ hiển thị kết quả trên console, không lưu file')
    
    args = parser.parse_args()
    
    try:
        # Kết nối đến database
        engine = setup_database()
        
        # Liệt kê các thiết bị có dữ liệu nén
        if not args.compression_id and not args.device_id and not args.start_date:
            query = "SELECT DISTINCT device_id FROM compressed_data_optimized ORDER BY device_id"
            with engine.connect() as conn:
                result = conn.execute(text(query))
                devices = [row[0] for row in result]
                
            if devices:
                logger.info("Danh sách các thiết bị có dữ liệu nén:")
                for device in devices:
                    logger.info(f"  - {device}")
            else:
                logger.warning("Không tìm thấy thiết bị nào trong database")
            return
            
        # Tìm bản ghi nén
        if args.compression_id:
            # Tìm theo compression_id
            compression_record = get_compression_record(engine, args.compression_id)
            records = [compression_record] if compression_record else []
        elif args.device_id and args.start_date and args.end_date:
            # Tìm theo device_id và khoảng thời gian
            records = find_compression_by_time_range(
                engine, 
                args.start_date, 
                args.end_date, 
                args.device_id, 
                args.limit
            )
        elif args.device_id:
            # Tìm theo device_id
            with engine.connect() as conn:
                records = find_compression_by_device_id(conn, args.device_id, args.limit)
        else:
            logger.warning("Không có đủ tham số để thực hiện giải nén")
            return
            
        # Kiểm tra kết quả tìm kiếm
        if not records:
            logger.warning("Không tìm thấy bản ghi nén nào phù hợp với điều kiện")
            return
            
        # Nếu chỉ liệt kê các bản ghi nén
        if args.list and records:
            print(f"\n=== DANH SÁCH BẢN GHI NÉN" + (f" CHO THIẾT BỊ '{args.device_id}'" if args.device_id else "") + " ===")
            for i, record in enumerate(records, 1):
                record_id = record.get('id', 'N/A')
                device_id = record.get('device_id', 'N/A')
                time_range = record.get('time_range', 'N/A')
                
                metadata = record.get('metadata', {})
                total_values = metadata.get('total_values', 0)
                templates = metadata.get('num_templates', 0)
                comp_ratio = metadata.get('compression_ratio', 0)
                
                print(f"{i}. ID: {record_id}, Thiết bị: {device_id}")
                print(f"   Phạm vi thời gian: {time_range}")
                print(f"   Số điểm dữ liệu: {total_values}, Templates: {templates}, Tỷ lệ nén: {comp_ratio:.2f}")
                print()
            return
            
        # Nếu giải nén và hiển thị kết quả
        if records:
            # Chỉ giải nén bản ghi đầu tiên nếu không có output file
            if not args.output and len(records) > 1 and args.console_only:
                logger.info(f"Nhiều bản ghi phù hợp, chỉ giải nén bản ghi đầu tiên. Sử dụng --output để giải nén tất cả.")
                records = [records[0]]
                
            # Giải nén từng bản ghi
            all_results = []
            for record in records:
                result = decompress_data(record)
                if result:
                    all_results.append(result)
                    
            if not all_results:
                logger.warning("Không thể giải nén dữ liệu")
                return
                
            # Nếu có nhiều bản ghi, kết hợp chúng
            if len(all_results) > 1:
                combined_results = {
                    'device_id': all_results[0]['device_id'],
                    'metadata': {
                        'num_records': len(all_results),
                        'total_values': sum(r['metadata'].get('total_values', 0) for r in all_results),
                        'num_templates': sum(r['metadata'].get('num_templates', 0) for r in all_results)
                    },
                    'decompressed_data': []
                }
                
                # Kết hợp tất cả dữ liệu giải nén
                for result in all_results:
                    combined_results['decompressed_data'].extend(result.get('decompressed_data', []))
                    
                # Sắp xếp lại theo thời gian nếu có
                if all(block.get('start_time') for block in combined_results['decompressed_data']):
                    combined_results['decompressed_data'].sort(key=lambda x: x['start_time'])
                    
                result_to_use = combined_results
            else:
                result_to_use = all_results[0]
                
            # Xác định tên file đầu ra
            output_file = args.output
            
            # Nếu không có output_file và không có tùy chọn chỉ hiển thị console, tạo tên file theo device_id
            if not output_file and not args.console_only:
                device_id = result_to_use['device_id']
                output_file = f"{device_id}.json"
                
            # Lưu kết quả vào file nếu được chỉ định hoặc tự động tạo
            if output_file:
                save_decompressed_data(result_to_use, output_file)
                # Nếu chỉ cần lưu file, không hiển thị trên console, thoát luôn
                if not args.console_only and not args.device_id:
                    return
            
            # Hiển thị kết quả
            # Hiển thị thông tin chung
            print("\n===== KẾT QUẢ GIẢI NÉN =====")
            print(f"Thiết bị: {result_to_use['device_id']}")
            print(f"Số lượng templates: {result_to_use['metadata'].get('num_templates', 0)}")
            print(f"Tổng số điểm dữ liệu: {result_to_use['metadata'].get('total_values', 0)}")
            print(f"Tỷ lệ nén: {result_to_use['metadata'].get('compression_ratio', 0):.2f}")
            
            # Hiển thị thông tin thời gian
            if 'time_range' in result_to_use['metadata']:
                print(f"Phạm vi thời gian: {result_to_use['metadata']['time_range']}")
                
            # Hiển thị dữ liệu mẫu - hiển thị 5 block đầu tiên
            print("\n--- DỮLIỆU MẪU ---")
            display_count = min(5, len(result_to_use.get('decompressed_data', [])))
            
            for i, block in enumerate(result_to_use.get('decompressed_data', [])[:display_count]):
                template_id = block.get('template_id', 'N/A')
                
                # Hiển thị thông tin thời gian của block
                time_info = ""
                if block.get('start_time') and block.get('end_time'):
                    time_info = f" (Từ {block['start_time']} đến {block['end_time']})"
                elif block.get('start_time'):
                    time_info = f" (Thời gian {block['start_time']})"
                elif block.get('timestamp'):
                    time_info = f" (Thời gian {block['timestamp']})"
                    
                print(f"\nBlock {i+1}, Template ID: {template_id}{time_info}")
                
                # In thông tin chi tiết về thời gian nếu người dùng yêu cầu
                if args.show_time:
                    for time_field in ['start_time', 'end_time', 'timestamp']:
                        if time_field in block:
                            print(f"  {time_field}: {block[time_field]}")
                
                # Hiển thị dữ liệu
                values = block.get('values', [])
                
                if isinstance(values, dict):
                    # Nếu values là dictionary, hiển thị tất cả các giá trị
                    for key, data_values in values.items():
                        if isinstance(data_values, (list, tuple, np.ndarray)):
                            print(f"  Dữ liệu [{key}]: {data_values[:10]}...")
                            if len(data_values) > 10:
                                print(f"  (Hiển thị 10/{len(data_values)} điểm dữ liệu)")
                        else:
                            print(f"  Dữ liệu [{key}]: {data_values}")
                else:
                    # Dữ liệu một chiều
                    if isinstance(values, (list, tuple, np.ndarray)):
                        print(f"  Dữ liệu: {values[:10]}...")
                        if len(values) > 10:
                            print(f"  (Hiển thị 10/{len(values)} điểm dữ liệu)")
                    else:
                        print(f"  Dữ liệu: {values}")
            
            # Thông báo thêm
            if display_count < len(result_to_use.get('decompressed_data', [])):
                remaining = len(result_to_use['decompressed_data']) - display_count
                print(f"\n(Còn {remaining} block khác không được hiển thị. Lưu vào file để xem đầy đủ.)")
                
            # Hiển thị thông tin về đường dẫn file đã lưu nếu có
            if output_file:
                print(f"\nKết quả đã được lưu vào file: {output_file}")
                
    except Exception as e:
        logger.error(f"Lỗi khi thực thi script: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 