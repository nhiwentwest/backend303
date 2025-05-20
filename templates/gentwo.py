#!/usr/bin/env python3
"""
Script để tạo dữ liệu giả lập có 2 mẫu template khác nhau và lưu vào bảng original_samples.

Mục tiêu là tạo ra dữ liệu trong 1 tuần (2016 điểm, cách 5 phút) với hai mẫu phân phối khác nhau:
1. Mẫu ngày làm việc (thứ 2 - thứ 6): Có đặc trưng riêng của người đi làm
2. Mẫu ngày cuối tuần (thứ 7 - chủ nhật): Có đặc trưng riêng của người nghỉ ngơi

Cách sử dụng:
    python3 gentwo.py [--device-id DEVICE_ID] [--start-date YYYY-MM-DD] 
                      [--num-days NUM_DAYS] [--no-save-db] [--user-id USER_ID]

Tham số:
    --device-id: ID của thiết bị cảm biến (mặc định: 'template_two')
    --start-date: Ngày bắt đầu tạo dữ liệu (định dạng YYYY-MM-DD)
    --num-days: Số ngày cần tạo dữ liệu (mặc định: 7, đề xuất: 30 để thấy đầy đủ các mẫu)
    --no-save-db: Không lưu dữ liệu vào database
    --user-id: ID của người dùng sở hữu thiết bị (mặc định: 1 - admin)
    
Lưu ý:
    - Nếu thiết bị chưa tồn tại, script sẽ tự động tạo mới thiết bị với user_id tương ứng
    - Dữ liệu được tạo gồm nhiệt độ, độ ẩm, áp suất và công suất, nhưng chỉ lưu giá trị công suất
    - Thời gian tạo dữ liệu (created_at) sẽ sử dụng thời gian máy cục bộ tại thời điểm lưu
"""

import os
import sys
import logging
import argparse
import random
import math
import datetime
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.StreamHandler(),
                       logging.FileHandler("gentwo.log")
                   ])
logger = logging.getLogger(__name__)

# Tải biến môi trường
load_dotenv()

# Kết nối database từ biến môi trường
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5433/iot_db")

def setup_database():
    """
    Thiết lập kết nối đến database và đảm bảo bảng original_samples đã được tạo
    
    Returns:
        engine: SQLAlchemy engine, hoặc None nếu không thể kết nối
    """
    try:
        # Tạo engine kết nối đến database
        engine = create_engine(DATABASE_URL)
        
        # Kiểm tra kết nối
        with engine.connect() as conn:
            # Tạo bảng devices nếu chưa tồn tại (chỉ với các trường cơ bản)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS devices (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR UNIQUE NOT NULL,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Tạo index cho bảng devices
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_devices_id ON devices (id);
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_device_id ON devices (device_id);
                    CREATE INDEX IF NOT EXISTS ix_devices_user_id ON devices (user_id);
                """))
            except Exception as e:
                logger.warning(f"Không thể tạo index cho bảng devices: {str(e)}")
            
            # Tạo bảng original_samples nếu chưa tồn tại (chỉ với các trường cơ bản)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS original_samples (
                    id SERIAL PRIMARY KEY,
                    device_id VARCHAR NOT NULL,
                    value NUMERIC(10,2) NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id)
                )
            """))
            
            # Tạo index cho bảng original_samples
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_original_samples_device_id ON original_samples (device_id);
                    CREATE INDEX IF NOT EXISTS idx_original_samples_timestamp ON original_samples (timestamp);
                """))
            except Exception as e:
                logger.warning(f"Không thể tạo index cho bảng original_samples: {str(e)}")
            
            conn.commit()
            
        logger.info(f"Đã kết nối thành công đến database: {DATABASE_URL}")
        return engine
    except Exception as e:
        logger.error(f"Lỗi khi kết nối đến database: {str(e)}")
        return None

def generate_workday_pattern(point_time: datetime, base_temp=22.0, base_humidity=65.0) -> float:
    """
    Tạo mẫu dữ liệu cho ngày làm việc (Thứ 2 - Thứ 6)
    
    Đặc trưng:
    - Thứ 2: Điện năng tiêu thụ cao sau nghỉ cuối tuần (các thiết bị cần khởi động lại)
    - Thứ 6: Điện năng tăng cao vào buổi tối (chuẩn bị cho cuối tuần)
    - Sáng sớm (6-8h): Tăng công suất nhanh (chuẩn bị đi làm)
    - Giữa ngày (9-16h): Công suất thấp (đi làm)
    - Chiều tối (17-22h): Công suất cao và ổn định (về nhà)
    - Đêm khuya (23-5h): Công suất rất thấp (ngủ)
    - Mùa: Điện năng tiêu thụ cao hơn vào mùa hè và mùa đông, thấp hơn vào mùa xuân và thu
    
    Args:
        point_time: Thời điểm dữ liệu
        base_temp, base_humidity: Giá trị cơ bản (giữ lại để tương thích với code cũ)
        
    Returns:
        float: Giá trị công suất điện
    """
    hour = point_time.hour
    minute = point_time.minute
    weekday = point_time.weekday()  # 0 = Thứ 2, 1 = Thứ 3, ..., 4 = Thứ 6
    day_of_month = point_time.day
    month = point_time.month
    
    # Tính giờ dạng thập phân (ví dụ: 8:30 = 8.5)
    decimal_hour = hour + minute / 60.0
    
    # Thêm nhiễu ngẫu nhiên theo ngày
    day_of_year = point_time.timetuple().tm_yday
    noise_factor = math.sin(day_of_year / 10.0) * 2.0  # Yếu tố nhiễu theo ngày trong năm
    
    # ------ YẾU TỐ MÙA ------
    # Việt Nam có 4 mùa rõ rệt ở miền Bắc, 2 mùa ở miền Nam
    # Mùa hè (tháng 5-8): Sử dụng điều hòa nhiều, tiêu thụ điện cao
    # Mùa đông (tháng 11-2): Sử dụng máy sưởi, tiêu thụ điện cao
    # Mùa xuân và thu (tháng 3-4, 9-10): Thời tiết dễ chịu, tiêu thụ điện thấp hơn
    seasonal_factor = 1.0
    
    if 5 <= month <= 8:  # Mùa hè
        seasonal_factor = 1.3 + 0.2 * math.sin(day_of_year / 30.0)  # Dao động theo đợt nóng
        # Đỉnh điểm mùa hè là tháng 6-7
        if month in [6, 7]:
            seasonal_factor += 0.2
    elif 11 <= month or month <= 2:  # Mùa đông
        seasonal_factor = 1.2 + 0.15 * math.sin(day_of_year / 20.0)  # Dao động theo đợt lạnh
        # Đỉnh điểm mùa đông là tháng 12-1
        if month == 12 or month == 1:
            seasonal_factor += 0.15
    else:  # Mùa xuân & thu
        seasonal_factor = 0.9 + 0.1 * math.sin(day_of_year / 15.0)
    
    # ------ YẾU TỐ NGÀY TRONG TUẦN ------
    # Điều chỉnh yếu tố nhiễu theo từng ngày trong tuần
    if weekday == 0:  # Thứ 2 - nhiều biến động hơn sau cuối tuần
        noise_factor *= 1.8
        monday_factor = 1.25  # Tiêu thụ điện cao hơn vào thứ 2 (khởi động lại các thiết bị)
    elif weekday == 1:  # Thứ 3 - ổn định hơn
        noise_factor *= 0.9
        monday_factor = 1.05
    elif weekday == 2:  # Thứ 4 - biến động trung bình
        noise_factor *= 1.1
        monday_factor = 1.0
    elif weekday == 3:  # Thứ 5 - bắt đầu tăng
        noise_factor *= 1.2
        monday_factor = 1.1
    elif weekday == 4:  # Thứ 6 - biến động cao, chuẩn bị cho cuối tuần
        noise_factor *= 1.5
        monday_factor = 1.2
    
    # Điều chỉnh yếu tố nhiễu theo từng tuần trong tháng
    week_of_month = (day_of_month - 1) // 7 + 1
    if week_of_month == 1:  # Tuần đầu tháng - năng suất cao
        noise_factor *= 0.7  # ổn định hơn
        week_factor = 0.95  # Tiết kiệm điện hơn đầu tháng
    elif week_of_month == 2:  # Tuần thứ 2
        week_factor = 1.0
    elif week_of_month == 3:  # Tuần thứ 3
        week_factor = 1.05
    elif week_of_month == 4 or day_of_month > 25:  # Tuần cuối tháng - mệt mỏi
        noise_factor *= 1.4  # biến động nhiều hơn
        week_factor = 1.15  # Tiêu thụ nhiều điện hơn cuối tháng
    else:
        week_factor = 1.0
    
    # Điều chỉnh cơ bản cho công suất dựa trên ngày trong tuần
    power_weekday_factor = monday_factor * week_factor * seasonal_factor
    
    # ------ BUỔI SÁNG SỚM (0-5h): NGỦ ĐÊM ------
    if 0 <= decimal_hour < 5:
        # Công suất cơ bản thấp (mọi người đang ngủ)
        base_power = 50.0 * power_weekday_factor
        
        # --- Thứ 2 đêm khuya: Đặc trưng riêng ---
        if weekday == 0:
            # Thứ 2 đêm khuya: Có thể chuẩn bị đồ cho ngày làm việc đầu tuần
            device_prob = 0.18  # 18% xác suất hoạt động thiết bị
            device_intensity = 1.2  # Cường độ cao hơn
        # --- Thứ 6 đêm khuya: Đặc trưng riêng ---
        elif weekday == 4:
            # Thứ 6 đêm khuya: Có thể thức khuya hơn chuẩn bị cho cuối tuần
            device_prob = 0.15  # 15% xác suất hoạt động thiết bị
            device_intensity = 1.3  # Cường độ cao hơn
        # --- Các ngày khác ---
        else:
            device_prob = 0.08  # 8% xác suất cơ bản
            device_intensity = 1.0
        
        # Yếu tố mùa (vào mùa đông/hè, các thiết bị điều hòa nhiệt độ có thể hoạt động)
        if (month <= 2 or month >= 11) and hour <= 2:  # Mùa đông, đêm lạnh
            device_prob += 0.12  # Tăng xác suất sử dụng máy sưởi
            base_power *= 1.3  # Tăng công suất cơ bản
        elif 5 <= month <= 8 and hour >= 3:  # Mùa hè, sáng sớm
            device_prob += 0.10  # Tăng xác suất sử dụng điều hòa/quạt
            base_power *= 1.2  # Tăng công suất cơ bản
        
        # Thêm các đột biến ngẫu nhiên (thiết bị tự động hoạt động trong đêm)
        if random.random() < device_prob:
            random_spike = random.uniform(50, 120) * device_intensity
            power = base_power + random_spike + random.uniform(-5, 5)
        else:
            power = base_power + random.uniform(-5, 5)
            
        # Thêm đột biến theo giờ cụ thể
        # 2-3h sáng: Tủ lạnh hoạt động chu kỳ
        if 2 <= hour < 3 and minute % 20 < 5:
            power += random.uniform(20, 35)
            
    # ------ BUỔI SÁNG (5-8h): CHUẨN BỊ ĐI LÀM ------
    elif 5 <= decimal_hour < 8:
        # Các yếu tố đặc trưng theo ngày
        if weekday == 0:  # Thứ 2: chuẩn bị kỹ càng hơn, nhiều hoạt động hơn
            progress_factor = 1.3  # Tiến độ nhanh hơn 30%
            intensity_factor = 1.25  # Cường độ cao hơn 25%
        elif weekday == 4:  # Thứ 6: chuẩn bị nhanh hơn, ít hoạt động hơn
            progress_factor = 0.85  # Tiến độ chậm hơn 15%
            intensity_factor = 0.95  # Cường độ thấp hơn 5%
        else:
            progress_factor = 1.0
            intensity_factor = 1.0
            
        # Yếu tố mùa
        if 11 <= month or month <= 2:  # Mùa đông
            progress_factor *= 0.85  # Buổi sáng mùa đông khó dậy, chậm hơn
            intensity_factor *= 1.2  # Nhưng sử dụng nhiều thiết bị hơn (đun nước, sưởi)
        elif 5 <= month <= 8:  # Mùa hè
            progress_factor *= 1.1  # Buổi sáng mùa hè dậy sớm hơn
            
        # Tính tiến độ: Từ 5h đến 8h, tiêu thụ điện tăng dần khi mọi người thức dậy
        progress = (decimal_hour - 5) / 3 * progress_factor
        
        # Tăng dần từ ngưỡng thấp (ngủ) đến cao (sử dụng nhiều thiết bị)
        power = 50.0 + 250.0 * progress * power_weekday_factor * intensity_factor + noise_factor * 5 + random.uniform(-15, 25)
        
        # Đặc trưng sáng sớm thứ 2 (6-7h): Chuẩn bị cho tuần mới, sử dụng nhiều thiết bị
        if weekday == 0 and 6 <= decimal_hour < 7:
            # Tăng xác suất sử dụng nhiều thiết bị vào sáng thứ 2
            if random.random() < 0.35:  # 35% xác suất
                power += random.uniform(120, 280) * seasonal_factor
        
        # Đặc trưng sáng thứ 6 (6:30-7:30): Chuẩn bị nhanh
        elif weekday == 4 and 6.5 <= decimal_hour < 7.5:
            if random.random() < 0.25:  # 25% xác suất
                power += random.uniform(100, 200) * seasonal_factor
                
        # Yếu tố thời tiết mùa vụ 
        # Mùa đông, sáng sớm 6-7h: Sưởi ấm, đun nước nóng
        if (month == 12 or month <= 2) and 6 <= decimal_hour < 7:
            power += random.uniform(70, 150)
        # Mùa hè, sáng 7-8h: Sử dụng quạt, điều hòa nhẹ
        elif (6 <= month <= 8) and 7 <= decimal_hour < 8:
            power += random.uniform(50, 120)
                
    # ------ BAN NGÀY (8-17h): ĐI LÀM/ĐI HỌC ------
    elif 8 <= decimal_hour < 17:
        # Điều chỉnh theo ngày trong tuần
        if weekday == 0:  # Thứ 2: nhiều thiết bị hoạt động hơn (quên tắt)
            device_operation_prob = 0.12  # 12% xác suất
            daytime_factor = 1.15
        elif weekday == 1:  # Thứ 3: ổn định
            device_operation_prob = 0.05
            daytime_factor = 1.0
        elif weekday == 2:  # Thứ 4: trung bình
            device_operation_prob = 0.06
            daytime_factor = 1.05
        elif weekday == 3:  # Thứ 5: tăng nhẹ
            device_operation_prob = 0.07
            daytime_factor = 1.1
        elif weekday == 4:  # Thứ 6: ít thiết bị hoạt động hơn (đã tắt để chuẩn bị đi chơi)
            device_operation_prob = 0.09  # 9% xác suất
            daytime_factor = 1.2
            
        # Điều chỉnh theo mùa
        if 5 <= month <= 8:  # Mùa hè
            # Giờ trưa mùa hè: Có thể bật điều hòa hẹn giờ
            if 11 <= decimal_hour < 14:
                device_operation_prob += 0.15
                daytime_factor *= 1.4
        elif 11 <= month or month <= 2:  # Mùa đông
            # Buổi chiều mùa đông: Có thể bật máy sưởi hẹn giờ
            if 15 <= decimal_hour < 17:
                device_operation_prob += 0.12
                daytime_factor *= 1.3
        
        # Công suất cơ bản ban ngày (nhà vắng)
        base_power = 60.0 * power_weekday_factor * daytime_factor
        
        # Chu kỳ hoạt động của thiết bị tự động trong ngày (tủ lạnh, bơm nước, v.v.)
        hour_fraction = decimal_hour - int(decimal_hour)
        
        # Chu kỳ tủ lạnh (khoảng 15-20 phút mỗi giờ)
        fridge_active = hour_fraction < 0.3
        if fridge_active:
            fridge_power = 30.0 * math.sin(hour_fraction * 20) if hour_fraction < 0.25 else 0
            power = base_power + fridge_power + random.uniform(-10, 10)
        else:
            power = base_power + random.uniform(-10, 10)
            
        # Chu kỳ bơm nước (hoạt động vào đầu mỗi giờ chẵn)
        if hour % 2 == 0 and minute < 10:
            power += random.uniform(40, 100) * (1 - minute/10)
            
        # Thêm các đột biến tiêu thụ điện do thiết bị khác
        if random.random() < device_operation_prob:
            # Mùa hè: thiết bị tiêu thụ điện cao hơn
            if 5 <= month <= 8:
                power += random.uniform(80, 200)
            else:
                power += random.uniform(50, 150)
        
        # Đặc trưng cho thứ 2 giữa trưa (các thiết bị khởi động lại sau nghỉ)
        if weekday == 0 and 12 <= decimal_hour < 13:
            if random.random() < 0.3:  # 30% xác suất
                power += random.uniform(100, 250)
                
        # Đặc trưng cho thứ 6 chiều (chuẩn bị về sớm)
        if weekday == 4 and 15 <= decimal_hour < 17:
            if random.random() < 0.35:  # 35% xác suất
                power += random.uniform(80, 200)
                
    # ------ BUỔI TỐI (17-22h): VỀ NHÀ ------
    elif 17 <= decimal_hour < 22:
        # Các yếu tố theo ngày
        if weekday == 0:  # Thứ 2: mệt mỏi, ít hoạt động hơn
            evening_factor = 0.9
            evening_prob = 0.1  # Xác suất có đỉnh tiêu thụ
        elif weekday == 1:  # Thứ 3: hơi mệt mỏi
            evening_factor = 0.95
            evening_prob = 0.12
        elif weekday == 2:  # Thứ 4: hoạt động bình thường
            evening_factor = 1.0
            evening_prob = 0.15
        elif weekday == 3:  # Thứ 5: hoạt động tăng dần
            evening_factor = 1.1
            evening_prob = 0.2
        elif weekday == 4:  # Thứ 6: hoạt động nhiều hơn, giải trí cuối tuần
            evening_factor = 1.25
            evening_prob = 0.3
            
        # Điều chỉnh theo mùa
        if 5 <= month <= 8:  # Mùa hè
            # Tối mùa hè: sử dụng điều hòa nhiều
            evening_factor *= 1.4
            seasonal_boost = random.uniform(100, 250)
        elif 11 <= month or month <= 2:  # Mùa đông
            # Tối mùa đông: sử dụng máy sưởi, đun nước nóng
            evening_factor *= 1.3
            seasonal_boost = random.uniform(80, 200)
        else:  # Mùa xuân, thu
            seasonal_boost = random.uniform(30, 100)
        
        # Công suất cơ bản buổi tối (cao hơn so với ban ngày)
        base_power = 300.0 * power_weekday_factor * evening_factor
        
        # Các hoạt động tối (nấu ăn, giải trí)
        # Nấu ăn: 17-19h
        cooking_time = max(0, min(2, 19 - decimal_hour)) if decimal_hour < 19 else 0
        # Giải trí: 19-22h
        entertainment_time = max(0, min(3, decimal_hour - 19)) if decimal_hour >= 19 else 0
        
        # Điều chỉnh theo ngày trong tuần
        if weekday == 0:  # Thứ 2: nấu ăn đơn giản
            cooking_coef = 0.8
            entertainment_coef = 0.9
        elif weekday == 4:  # Thứ 6: nấu ăn phức tạp, giải trí nhiều
            cooking_coef = 1.25
            entertainment_coef = 1.4
        else:
            cooking_coef = 1.0
            entertainment_coef = 1.0
        
        cooking_power = 150.0 * cooking_time * cooking_coef if cooking_time > 0 else 0
        entertainment_power = 100.0 * entertainment_time * entertainment_coef if entertainment_time > 0 else 0
        
        # Công suất cơ bản + hoạt động + nhiễu + mùa
        power = base_power + cooking_power + entertainment_power + noise_factor * 15 + random.uniform(-20, 50)
        
        # Tăng đột biến khi bật thiết bị lớn (điều hòa, máy giặt, v.v.)
        if random.random() < evening_prob:
            # Mùa hè/đông: tăng mạnh hơn do sử dụng thiết bị điều chỉnh nhiệt độ
            if (5 <= month <= 8) or (month <= 2 or month >= 11):
                power += seasonal_boost * 1.5
            else:
                power += seasonal_boost
            
        # Đặc trưng thứ 6 tối: tiệc tùng, hoạt động nhiều hơn
        if weekday == 4 and decimal_hour >= 20:
            if random.random() < 0.4:  # 40% xác suất
                power += random.uniform(150, 300)
                
        # Đặc trưng theo giờ cụ thể và ngày
        # 21-22h thứ 2: Giặt đồ cho tuần mới
        if weekday == 0 and 21 <= decimal_hour < 22:
            if random.random() < 0.35:
                power += random.uniform(200, 350)
                
        # 20-21h thứ 5: Chuẩn bị đồ cho ngày thứ 6 và cuối tuần
        if weekday == 3 and 20 <= decimal_hour < 21:
            if random.random() < 0.3:
                power += random.uniform(150, 250)
                
    # ------ ĐÊM MUỘN (22-24h): CHUẨN BỊ ĐI NGỦ ------
    elif 22 <= decimal_hour < 24:
        # Điều chỉnh theo ngày trong tuần
        if weekday == 0:  # Thứ 2: đi ngủ sớm hơn
            sleep_factor = 1.3  # Nhanh hơn 30%
            late_night_factor = 0.8
        elif weekday == 1:  # Thứ 3: đi ngủ khá sớm
            sleep_factor = 1.2
            late_night_factor = 0.85
        elif weekday == 2:  # Thứ 4: trung bình
            sleep_factor = 1.0
            late_night_factor = 1.0
        elif weekday == 3:  # Thứ 5: hơi muộn
            sleep_factor = 0.9
            late_night_factor = 1.1
        elif weekday == 4:  # Thứ 6: đi ngủ muộn hơn (chuẩn bị cho cuối tuần)
            sleep_factor = 0.7  # Chậm hơn 30%
            late_night_factor = 1.3
            
        # Điều chỉnh theo mùa
        if 5 <= month <= 8:  # Mùa hè - đêm nóng
            night_seasonal_factor = 1.3  # Sử dụng quạt, điều hòa đi ngủ
        elif 11 <= month or month <= 2:  # Mùa đông - đêm lạnh
            night_seasonal_factor = 1.25  # Sử dụng máy sưởi, chăn điện
        else:
            night_seasonal_factor = 1.0
        
        # Giảm dần từ 22h-24h với dao động phức tạp
        progress = (decimal_hour - 22) / 2 * sleep_factor
        power = 300.0 - 220.0 * progress + noise_factor * 10 + random.uniform(-20, 20)
        
        # Điều chỉnh theo ngày và mùa
        power *= late_night_factor * night_seasonal_factor
        
        # Đỉnh điện cuối ngày khi vệ sinh cá nhân
        if 22 <= decimal_hour < 22.5:
            # Thứ 2: vệ sinh nhanh hơn
            if weekday == 0:
                hygiene_factor = 0.8
            # Thứ 6: vệ sinh kỹ hơn
            elif weekday == 4:
                hygiene_factor = 1.3
            else:
                hygiene_factor = 1.0
                
            power += random.uniform(20, 100) * (1 - (decimal_hour - 22) * 2) * hygiene_factor
            
        # Thứ 6 đêm: Chuẩn bị cho cuối tuần, thức khuya hơn
        if weekday == 4 and decimal_hour >= 23:
            if random.random() < 0.4:
                power += random.uniform(100, 200) * night_seasonal_factor
    
    # Biến động theo tuần của tháng
    if week_of_month == 1:  # Tuần đầu tháng: tiết kiệm hơn
        power *= 0.92
    elif week_of_month == 2:  # Tuần thứ hai
        power *= 0.98
    elif week_of_month == 3:  # Tuần thứ ba
        power *= 1.03
    elif week_of_month == 4 or day_of_month > 25:  # Tuần cuối tháng: tiêu thụ nhiều hơn
        power *= 1.1
    
    # Chỉ trả về power thay vì dict
    return round(power, 2)

def generate_weekend_pattern(point_time: datetime, base_temp=23.0, base_humidity=62.0) -> float:
    """
    Tạo mẫu dữ liệu cho ngày cuối tuần (Thứ 7 - Chủ nhật)
    
    Đặc trưng:
    - Thứ 7: Hoạt động nhiều hơn, tổ chức tiệc, dọn dẹp nhà cửa, giặt giũ
    - Chủ nhật: Nghỉ ngơi, hoạt động ít hơn, chuẩn bị cho tuần mới
    - Sáng sớm (0-7h): Công suất rất thấp (ngủ muộn)
    - Buổi sáng (7-11h): Tăng nhẹ, từ từ (ngủ dậy muộn)
    - Buổi trưa-chiều (11-17h): Hoạt động cao (nấu nướng, giặt giũ, dọn dẹp)
    - Tối muộn (17-24h): Rất cao (tiệc tùng, giải trí)
    - Mùa: Điện năng tiêu thụ cao hơn vào mùa hè và mùa đông, thấp hơn vào mùa xuân và thu
    
    Args:
        point_time: Thời điểm dữ liệu
        base_temp, base_humidity: Giá trị cơ bản (giữ lại để tương thích với code cũ)
        
    Returns:
        float: Giá trị công suất điện
    """
    hour = point_time.hour
    minute = point_time.minute
    weekday = point_time.weekday()  # 5 = Thứ 7, 6 = Chủ nhật
    day_of_month = point_time.day
    month = point_time.month
    
    # Tính giờ dạng thập phân (ví dụ: 8:30 = 8.5)
    decimal_hour = hour + minute / 60.0
    
    # Thêm nhiễu ngẫu nhiên theo ngày
    day_of_year = point_time.timetuple().tm_yday
    noise_factor = math.sin(day_of_year / 10.0) * 2.5  # Nhiễu cao hơn cho cuối tuần
    
    # ------ YẾU TỐ MÙA ------
    # Việt Nam có 4 mùa rõ rệt ở miền Bắc, 2 mùa ở miền Nam
    # Mùa hè (tháng 5-8): Sử dụng điều hòa nhiều, tiêu thụ điện cao
    # Mùa đông (tháng 11-2): Sử dụng máy sưởi, tiêu thụ điện cao
    # Mùa xuân và thu (tháng 3-4, 9-10): Thời tiết dễ chịu, tiêu thụ điện thấp hơn
    seasonal_factor = 1.0
    
    if 5 <= month <= 8:  # Mùa hè
        seasonal_factor = 1.4 + 0.25 * math.sin(day_of_year / 25.0)  # Dao động theo đợt nóng
        # Đỉnh điểm mùa hè là tháng 6-7
        if month in [6, 7]:
            seasonal_factor += 0.25
    elif 11 <= month or month <= 2:  # Mùa đông
        seasonal_factor = 1.3 + 0.2 * math.sin(day_of_year / 15.0)  # Dao động theo đợt lạnh
        # Đỉnh điểm mùa đông là tháng 12-1
        if month == 12 or month == 1:
            seasonal_factor += 0.2
    else:  # Mùa xuân & thu
        seasonal_factor = 0.9 + 0.15 * math.sin(day_of_year / 12.0)
    
    # ------ YẾU TỐ NGÀY TRONG TUẦN ------
    # Điều chỉnh yếu tố nhiễu theo từng ngày trong tuần
    if weekday == 5:  # Thứ 7 - nhiều hoạt động hơn, dọn dẹp, tiệc tùng
        noise_factor *= 1.5
        weekend_factor = 1.35  # Tiêu thụ điện cao hơn vào thứ 7
    elif weekday == 6:  # Chủ nhật - nghỉ ngơi, ít biến động hơn
        noise_factor *= 0.8
        weekend_factor = 1.15  # Tiêu thụ điện thấp hơn vào chủ nhật
    
    # Điều chỉnh yếu tố nhiễu theo từng tuần trong tháng
    week_of_month = (day_of_month - 1) // 7 + 1
    if week_of_month == 1:  # Tuần đầu tháng - năng suất cao
        noise_factor *= 0.8  # ổn định hơn
        week_factor = 0.9  # Tiết kiệm điện hơn đầu tháng
    elif week_of_month == 2:  # Tuần thứ 2
        week_factor = 1.0
    elif week_of_month == 3:  # Tuần thứ 3
        week_factor = 1.1
        noise_factor *= 1.2
    elif week_of_month == 4 or day_of_month > 25:  # Tuần cuối tháng - tiệc tùng
        noise_factor *= 1.5  # biến động nhiều hơn
        week_factor = 1.2  # Tiêu thụ nhiều điện hơn cuối tháng
    else:
        week_factor = 1.0
    
    # Điều chỉnh cơ bản cho công suất dựa trên ngày trong tuần và mùa
    power_weekend_factor = weekend_factor * week_factor * seasonal_factor
    
    # ------ BUỔI SÁNG SỚM (0-7h): NGỦ MUỘN ------
    if 0 <= decimal_hour < 7:
        # Công suất cơ bản thấp (mọi người đang ngủ)
        base_power = 45.0 * power_weekend_factor
        
        # --- Thứ 7 đêm khuya/sáng sớm: Đặc trưng riêng ---
        if weekday == 5:
            # Thứ 7 đêm khuya: Thức khuya hơn, hoạt động nhiều hơn
            if decimal_hour < 2:  # Khoảng 0-2h sáng
                device_prob = 0.35  # 35% xác suất hoạt động thiết bị
                device_intensity = 1.4  # Cường độ cao hơn
            else:  # 2-7h sáng
                device_prob = 0.15  # 15% xác suất
                device_intensity = 1.1
        # --- Chủ nhật đêm khuya: Đặc trưng riêng ---
        elif weekday == 6:
            # Chủ nhật đêm khuya: Nghỉ ngơi nhiều hơn, chuẩn bị cho tuần làm việc
            if decimal_hour < 2:  # 0-2h sáng
                device_prob = 0.2  # 20% xác suất hoạt động thiết bị
                device_intensity = 1.2  # Cường độ thấp hơn thứ 7
            else:  # 2-7h sáng
                device_prob = 0.08  # 8% xác suất (ngủ sâu)
                device_intensity = 0.9
        
        # Yếu tố mùa (vào mùa đông/hè, các thiết bị điều hòa nhiệt độ có thể hoạt động)
        if (month <= 2 or month >= 11):  # Mùa đông
            if hour <= 2:  # Đêm đông lạnh
                device_prob += 0.15  # Tăng xác suất sử dụng máy sưởi
                base_power *= 1.4  # Tăng công suất cơ bản 
            else:  # Sáng đông lạnh  
                device_prob += 0.1
                base_power *= 1.25
        elif 5 <= month <= 8:  # Mùa hè
            if hour >= 3:  # Sáng sớm nóng
                device_prob += 0.12  # Tăng xác suất sử dụng điều hòa/quạt
                base_power *= 1.3  # Tăng công suất cơ bản
            else:  # Đêm hè nóng
                device_prob += 0.15
                base_power *= 1.35
        
        # Thêm các đột biến ngẫu nhiên (thiết bị tự động hoạt động trong đêm)
        if random.random() < device_prob:
            random_spike = random.uniform(60, 150) * device_intensity
            power = base_power + random_spike + random.uniform(-8, 12)
        else:
            power = base_power + random.uniform(-8, 12)
            
        # Thêm đột biến theo giờ cụ thể
        # Tủ lạnh hoạt động chu kỳ
        if minute % 20 < 8:  # Khoảng 8 phút mỗi 20 phút
            power += random.uniform(25, 45)
            
    # ------ BUỔI SÁNG (7-11h): DẬY MUỘN, HOẠT ĐỘNG TĂNG DẦN ------
    elif 7 <= decimal_hour < 11:
        # Các yếu tố đặc trưng theo ngày
        if weekday == 5:  # Thứ 7: dọn dẹp, hoạt động nhiều
            progress_factor = 1.2  # Tiến độ nhanh hơn 20%
            intensity_factor = 1.3  # Cường độ cao hơn 30%
        elif weekday == 6:  # Chủ nhật: dậy muộn, thư giãn
            progress_factor = 0.8  # Tiến độ chậm hơn 20%
            intensity_factor = 0.9  # Cường độ thấp hơn 10%
            
        # Yếu tố mùa
        if 11 <= month or month <= 2:  # Mùa đông
            progress_factor *= 0.9  # Buổi sáng mùa đông khó dậy, chậm hơn
            intensity_factor *= 1.25  # Nhưng sử dụng nhiều thiết bị hơn (đun nước, sưởi)
        elif 5 <= month <= 8:  # Mùa hè
            progress_factor *= 1.1  # Buổi sáng mùa hè dậy sớm hơn
            intensity_factor *= 1.2  # Sử dụng quạt, điều hòa
            
        # Tính tiến độ: Từ 7h đến 11h, tiêu thụ điện tăng dần khi mọi người thức dậy
        progress = (decimal_hour - 7) / 4 * progress_factor
        
        # Tăng dần từ ngưỡng thấp (ngủ) đến cao (hoạt động)
        base_weekend_power = 75.0 + 300.0 * progress
        power = base_weekend_power * power_weekend_factor * intensity_factor + noise_factor * 8 + random.uniform(-20, 30)
        
        # Đặc trưng cho thứ 7 sáng: dọn dẹp, giặt giũ, hoạt động nhiều
        if weekday == 5:
            # 8-10h: Cao điểm hoạt động sáng thứ 7
            if 8 <= decimal_hour < 10:
                cleaning_prob = 0.4 + (decimal_hour - 8) * 0.1  # Tăng dần từ 40% đến 60%
                if random.random() < cleaning_prob:
                    power += random.uniform(150, 350) * seasonal_factor
            # 10-11h: Đi chợ, chuẩn bị ăn trưa
            elif 10 <= decimal_hour < 11:
                if random.random() < 0.3:
                    power += random.uniform(100, 250) * seasonal_factor
        
        # Đặc trưng cho chủ nhật sáng: thư giãn, ít hoạt động
        elif weekday == 6:
            # 9-11h: Chuẩn bị ăn trưa, hoạt động nhẹ
            if 9 <= decimal_hour < 11:
                relax_prob = 0.25
                if random.random() < relax_prob:
                    power += random.uniform(80, 180) * seasonal_factor
                
        # Yếu tố thời tiết mùa vụ 
        # Mùa đông, sáng 8-10h: Sưởi ấm, đun nước nóng
        if (month <= 2 or month >= 11) and 8 <= decimal_hour < 10:
            power += random.uniform(100, 200)
        # Mùa hè, sáng 9-11h: Sử dụng quạt, điều hòa
        elif (5 <= month <= 8) and 9 <= decimal_hour < 11:
            power += random.uniform(120, 250)
                
    # ------ BUỔI TRƯA-CHIỀU (11-17h): HOẠT ĐỘNG NHIỀU ------
    elif 11 <= decimal_hour < 17:
        # Điều chỉnh theo ngày cuối tuần
        if weekday == 5:  # Thứ 7: dọn dẹp, hoạt động nhiều
            activity_prob = 0.5  # 50% xác suất hoạt động cao
            daytime_factor = 1.3
        elif weekday == 6:  # Chủ nhật: nghỉ ngơi nhiều hơn, chuẩn bị cho tuần mới
            activity_prob = 0.35  # 35% xác suất
            daytime_factor = 1.1
            
        # Điều chỉnh theo mùa
        if 5 <= month <= 8:  # Mùa hè
            # Giờ trưa mùa hè: Sử dụng điều hòa nhiều
            if 12 <= decimal_hour < 15:
                activity_prob += 0.2
                daytime_factor *= 1.5
                summer_boost = random.uniform(150, 300)
            else:
                summer_boost = random.uniform(100, 200)
        elif 11 <= month or month <= 2:  # Mùa đông
            # Buổi chiều mùa đông: Sử dụng máy sưởi nhiều
            if 14 <= decimal_hour < 17:
                activity_prob += 0.15
                daytime_factor *= 1.4
                winter_boost = random.uniform(120, 250)
            else:
                winter_boost = random.uniform(80, 180)
        else:
            summer_boost = winter_boost = 0
        
        # Công suất cơ bản ban ngày cuối tuần (ở nhà, hoạt động nhiều)
        base_power = 150.0 * power_weekend_factor * daytime_factor
        
        # Hoạt động trưa: nấu nướng, ăn uống (11-13h)
        lunch_time = max(0, min(2, 13 - decimal_hour)) if decimal_hour < 13 else 0
        # Hoạt động chiều: dọn dẹp, giặt giũ (13-17h)
        afternoon_time = max(0, min(4, decimal_hour - 13)) if decimal_hour >= 13 else 0
        
        # Điều chỉnh theo ngày cuối tuần
        if weekday == 5:  # Thứ 7: nấu nướng nhiều, hoạt động mạnh
            lunch_factor = 1.3
            afternoon_factor = 1.4
        elif weekday == 6:  # Chủ nhật: nấu ăn đơn giản, nghỉ ngơi
            lunch_factor = 1.1
            afternoon_factor = 0.9
            
        lunch_power = 200.0 * lunch_time * lunch_factor if lunch_time > 0 else 0
        afternoon_power = 180.0 * afternoon_time * afternoon_factor if afternoon_time > 0 else 0
        
        # Công suất = cơ bản + ăn trưa + hoạt động chiều + nhiễu
        power = base_power + lunch_power + afternoon_power + noise_factor * 12 + random.uniform(-25, 35)
        
        # Thêm các đột biến ngẫu nhiên từ các hoạt động cao điểm
        if random.random() < activity_prob:
            # Thứ 7: hoạt động mạnh (giặt giũ, dọn dẹp, sửa chữa)
            if weekday == 5:
                high_activity_boost = random.uniform(150, 350)
                # Mùa hè/đông: cộng thêm thiết bị điều hòa nhiệt độ
                if (5 <= month <= 8):
                    power += high_activity_boost + summer_boost
                elif (month <= 2 or month >= 11):
                    power += high_activity_boost + winter_boost
                else:
                    power += high_activity_boost
            # Chủ nhật: hoạt động nhẹ hơn, chủ yếu giải trí
            else:
                mild_activity_boost = random.uniform(100, 250)
                # Mùa hè/đông: cộng thêm thiết bị điều hòa nhiệt độ
                if (5 <= month <= 8):
                    power += mild_activity_boost + summer_boost
                elif (month <= 2 or month >= 11):
                    power += mild_activity_boost + winter_boost
                else:
                    power += mild_activity_boost
                    
        # Hoạt động đặc trưng theo giờ và ngày
        # Thứ 7 trưa (12-13h): Nấu ăn lớn cho cuối tuần
        if weekday == 5 and 12 <= decimal_hour < 13:
            if random.random() < 0.6:  # 60% xác suất
                power += random.uniform(200, 400)
                
        # Thứ 7 chiều (15-17h): Dọn dẹp, giặt giũ cao điểm
        elif weekday == 5 and 15 <= decimal_hour < 17:
            if random.random() < 0.55:  # 55% xác suất
                power += random.uniform(180, 350)
                
        # Chủ nhật trưa (12-14h): Nấu ăn, gặp gỡ gia đình
        elif weekday == 6 and 12 <= decimal_hour < 14:
            if random.random() < 0.5:  # 50% xác suất
                power += random.uniform(150, 300)
                
        # Chủ nhật chiều (15-17h): Chuẩn bị cho tuần mới
        elif weekday == 6 and 15 <= decimal_hour < 17:
            if random.random() < 0.4:  # 40% xác suất
                power += random.uniform(120, 250)
                
    # ------ TỐI CUỐI TUẦN (17-24h): GIẢI TRÍ CAO ĐIỂM ------
    elif 17 <= decimal_hour < 24:
        # Các yếu tố theo ngày cuối tuần
        if weekday == 5:  # Thứ 7 tối: tiệc tùng, giải trí cao điểm
            evening_factor = 1.4
            evening_prob = 0.6  # Xác suất có đỉnh tiêu thụ cao
        elif weekday == 6:  # Chủ nhật tối: giải trí nhẹ, chuẩn bị cho tuần mới
            evening_factor = 1.1
            evening_prob = 0.35
            
        # Điều chỉnh theo mùa
        if 5 <= month <= 8:  # Mùa hè
            # Tối mùa hè: sử dụng điều hòa nhiều
            evening_factor *= 1.5
            seasonal_boost = random.uniform(150, 300)
        elif 11 <= month or month <= 2:  # Mùa đông
            # Tối mùa đông: sử dụng máy sưởi, đun nước nóng
            evening_factor *= 1.4
            seasonal_boost = random.uniform(130, 270)
        else:  # Mùa xuân, thu
            seasonal_boost = random.uniform(50, 150)
        
        # Công suất cơ bản buổi tối cuối tuần (cao hơn ngày thường)
        base_power = 350.0 * power_weekend_factor * evening_factor
        
        # Các hoạt động tối cuối tuần (nấu ăn, tiệc tùng, giải trí)
        # Nấu ăn: 17-20h (nấu ăn dài hơn vào cuối tuần)
        cooking_time = max(0, min(3, 20 - decimal_hour)) if decimal_hour < 20 else 0
        # Giải trí: 19-24h
        entertainment_time = max(0, min(5, decimal_hour - 19)) if decimal_hour >= 19 else 0
        
        # Điều chỉnh theo ngày cuối tuần
        if weekday == 5:  # Thứ 7: nấu ăn phức tạp, tiệc tùng, giải trí lớn
            cooking_coef = 1.4
            entertainment_coef = 1.5
        elif weekday == 6:  # Chủ nhật: nấu ăn đơn giản hơn, giải trí nhẹ nhàng
            cooking_coef = 1.1
            entertainment_coef = 1.0
        
        cooking_power = 200.0 * cooking_time * cooking_coef if cooking_time > 0 else 0
        entertainment_power = 150.0 * entertainment_time * entertainment_coef if entertainment_time > 0 else 0
        
        # Công suất = cơ bản + nấu ăn + giải trí + nhiễu
        power = base_power + cooking_power + entertainment_power + noise_factor * 20 + random.uniform(-30, 60)
        
        # Thêm đột biến cao điểm (tiệc tùng, máy giặt, điều hòa, v.v.)
        if random.random() < evening_prob:
            # Thứ 7 tối: tiệc tùng, hoạt động mạnh
            if weekday == 5:
                # Mùa hè/đông: tăng mạnh hơn do sử dụng thiết bị điều chỉnh nhiệt độ
                if (5 <= month <= 8) or (month <= 2 or month >= 11):
                    power += random.uniform(200, 400) + seasonal_boost
                else:
                    power += random.uniform(180, 350)
            # Chủ nhật tối: giải trí nhẹ nhàng hơn
            else:
                # Mùa hè/đông: tăng nhẹ do sử dụng thiết bị điều chỉnh nhiệt độ
                if (5 <= month <= 8) or (month <= 2 or month >= 11):
                    power += random.uniform(120, 300) + seasonal_boost * 0.8
                else:
                    power += random.uniform(100, 250)
            
        # Đặc trưng theo giờ cụ thể và ngày
        # 19-22h thứ 7: Tiệc tùng, hoạt động cao điểm
        if weekday == 5 and 19 <= decimal_hour < 22:
            party_prob = 0.7 - 0.1 * (decimal_hour - 19)  # Giảm dần từ 70% -> 40%
            if random.random() < party_prob:
                power += random.uniform(250, 500) * seasonal_factor
                
        # 22-24h thứ 7: Tiệc tùng kéo dài
        elif weekday == 5 and 22 <= decimal_hour < 24:
            late_party_prob = 0.5 - 0.15 * (decimal_hour - 22)  # Giảm dần từ 50% -> 20%
            if random.random() < late_party_prob:
                power += random.uniform(200, 400) * seasonal_factor
                
        # 19-21h chủ nhật: Giải trí gia đình
        elif weekday == 6 and 19 <= decimal_hour < 21:
            if random.random() < 0.5:
                power += random.uniform(150, 300) * seasonal_factor
                
        # 21-23h chủ nhật: Chuẩn bị cho tuần mới
        elif weekday == 6 and 21 <= decimal_hour < 23:
            if random.random() < 0.4:
                power += random.uniform(180, 350) * seasonal_factor
    
    # Biến động theo tuần của tháng
    if week_of_month == 1:  # Tuần đầu tháng: tiết kiệm hơn
        power *= 0.9
    elif week_of_month == 2:  # Tuần thứ hai
        power *= 0.98
    elif week_of_month == 3:  # Tuần thứ ba
        power *= 1.05
    elif week_of_month == 4 or day_of_month > 25:  # Tuần cuối tháng: tiêu thụ nhiều hơn
        power *= 1.15
    
    # Chỉ trả về power thay vì dict
    return round(power, 2)

def generate_template_data(num_days: int = 7, device_id: str = "template_two", start_date: Optional[datetime] = None, season: Optional[str] = None, num_points: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Tạo dữ liệu giả lập với các mẫu template đa dạng theo ngày và mùa
    
    Args:
        num_days: Số ngày cần tạo dữ liệu
        device_id: ID của thiết bị
        start_date: Thời gian bắt đầu (nếu None sẽ dùng thời gian hiện tại)
        season: Chỉ định mùa ('summer', 'winter', 'spring', 'autumn') hoặc None để dùng mùa hiện tại
        num_points: Số điểm dữ liệu cần tạo (nếu None sẽ tính từ num_days)
        
    Returns:
        Danh sách các điểm dữ liệu
    """
    # Kiểm tra device_id hợp lệ
    if not device_id or device_id == "final":
        logger.warning(f"Device ID '{device_id}' không hợp lệ. Sử dụng 'template_two' thay thế.")
        device_id = "template_two"
    
    # Log the device_id being used
    logger.info(f"Generating data for device_id: {device_id}")
    
    data_points = []
    
    # Tính số điểm dữ liệu (5 phút/điểm, 12 điểm/giờ, 288 điểm/ngày)
    points_per_day = 288  # 24 giờ * 12 điểm mỗi giờ
    if num_points is not None:
        total_points = num_points
    else:
        total_points = num_days * points_per_day
    
    # Tạo thời gian bắt đầu
    if start_date is None:
        # Sử dụng thời gian hiện tại (không cần reset về 00:00:00)
        current_time = datetime.now()
        # Làm tròn xuống 5 phút gần nhất
        minute_rounded = current_time.minute - (current_time.minute % 5)
        start_time = current_time.replace(minute=minute_rounded, second=0, microsecond=0)
        logger.info(f"Sử dụng thời gian hiện tại: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Tính thời gian bắt đầu của tuần (thứ 2) nếu dùng thời gian hiện tại
        days_to_monday = start_time.weekday()
        if days_to_monday > 0:
            # Nếu không phải thứ 2, điều chỉnh thời gian bắt đầu
            week_start = start_time - timedelta(days=days_to_monday)
            logger.info(f"Điều chỉnh thời gian bắt đầu về thứ Hai: {week_start.strftime('%Y-%m-%d')}")
        else:
            week_start = start_time
    else:
        # Sử dụng thời gian được chỉ định, giữ nguyên giờ và ngày được chỉ định
        start_time = start_date
        week_start = start_time  # Không điều chỉnh về thứ Hai khi người dùng chỉ định ngày cụ thể
        logger.info(f"Sử dụng thời gian được chỉ định: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Xử lý thông tin mùa (nếu được chỉ định)
    if season:
        original_month = week_start.month
        original_day = week_start.day  # Lưu lại ngày ban đầu
        
        # Hàm hỗ trợ điều chỉnh ngày nếu cần thiết
        def adjust_date_for_month(date, target_month):
            # Lấy số ngày tối đa trong tháng mới
            # Cách làm: Lấy ngày đầu tiên của tháng tiếp theo và trừ đi 1
            year = date.year
            # Điều chỉnh năm nếu tháng tiếp theo là tháng 1 (tháng hiện tại là 12)
            if target_month == 12:
                next_month_year = year
                next_month = 1
            else:
                next_month_year = year + 1 if target_month == 12 else year
                next_month = 1 if target_month == 12 else target_month + 1
                
            # Tạo ngày đầu tiên của tháng tiếp theo và trừ đi một ngày
            next_month_first_day = datetime(next_month_year, next_month, 1)
            last_day_of_target_month = (next_month_first_day - timedelta(days=1)).day
            
            # Đảm bảo ngày nằm trong phạm vi hợp lệ của tháng mới
            valid_day = min(date.day, last_day_of_target_month)
            
            # Tạo đối tượng datetime mới với ngày đã điều chỉnh
            return date.replace(month=target_month, day=valid_day)
        
        if season.lower() == 'summer':
            # Mùa hè: tháng 6-7
            new_month = random.choice([6, 7])
            logger.info(f"Chỉ định mùa HÈ: Điều chỉnh tháng từ {original_month} thành {new_month}")
            week_start = adjust_date_for_month(week_start, new_month)
        elif season.lower() == 'winter':
            # Mùa đông: tháng 12-1
            new_month = random.choice([12, 1])
            if new_month == 1 and original_month > 1:
                # Nếu chuyển từ tháng khác sang tháng 1, cần tăng năm lên 1
                logger.info(f"Chỉ định mùa ĐÔNG: Điều chỉnh tháng từ {original_month} thành {new_month} năm sau")
                # Điều chỉnh năm trước, sau đó điều chỉnh ngày
                week_start = week_start.replace(year=week_start.year + 1)
                week_start = adjust_date_for_month(week_start, new_month)
            else:
                logger.info(f"Chỉ định mùa ĐÔNG: Điều chỉnh tháng từ {original_month} thành {new_month}")
                week_start = adjust_date_for_month(week_start, new_month)
        elif season.lower() == 'spring':
            # Mùa xuân: tháng 3-4
            new_month = random.choice([3, 4])
            logger.info(f"Chỉ định mùa XUÂN: Điều chỉnh tháng từ {original_month} thành {new_month}")
            week_start = adjust_date_for_month(week_start, new_month)
        elif season.lower() == 'autumn':
            # Mùa thu: tháng 9-10
            new_month = random.choice([9, 10])
            logger.info(f"Chỉ định mùa THU: Điều chỉnh tháng từ {original_month} thành {new_month}")
            week_start = adjust_date_for_month(week_start, new_month)
        else:
            logger.warning(f"Mùa không hợp lệ: {season}. Sử dụng mùa hiện tại.")
        
        # Ghi log thông tin ngày sau khi điều chỉnh
        if week_start.day != original_day:
            logger.info(f"Đã điều chỉnh ngày từ {original_day} thành {week_start.day} để phù hợp với tháng {week_start.month}")
    
    # Xác định mùa
    month = week_start.month
    if 3 <= month <= 4:
        season_name = "Xuân"
    elif 5 <= month <= 8:
        season_name = "Hè"
    elif 9 <= month <= 10:
        season_name = "Thu"
    else:
        season_name = "Đông"
    
    logger.info(f"Bắt đầu tạo dữ liệu từ: {week_start.strftime('%Y-%m-%d %H:%M:%S')} (Mùa {season_name})")
    
    # Tạo điểm dữ liệu
    for i in range(total_points):
        # Mỗi điểm tăng đúng 5 phút
        point_time = week_start + timedelta(minutes=i * 5)
        
        # Xác định loại ngày
        weekday = point_time.weekday()
        
        # Tạo dữ liệu cảm biến dựa vào loại ngày
        if weekday < 5:  # Thứ 2 - Thứ 6
            value = generate_workday_pattern(point_time)
        else:  # Thứ 7 - Chủ nhật
            value = generate_weekend_pattern(point_time)
        
        # Tạo điểm dữ liệu - now value is a single float
        data_point = {
            "device_id": device_id,
            "timestamp": point_time,
            "value": value
        }
        
        data_points.append(data_point)
        
        # Hiển thị tiến trình
        if i % points_per_day == 0 or i == 0:
            current_date = point_time.strftime("%Y-%m-%d %H:%M:%S")
            day_name = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật'][weekday]
            logger.info(f"Đang tạo dữ liệu cho: {current_date} ({day_name}), device_id: {device_id}")
    
    # Thống kê chi tiết về dữ liệu đã tạo
    workdays = sum(1 for point in data_points if point['timestamp'].weekday() < 5)
    weekends = len(data_points) - workdays
    
    # Tính toán các số liệu thống kê
    weekday_values = [point['value'] for point in data_points if point['timestamp'].weekday() < 5]
    weekend_values = [point['value'] for point in data_points if point['timestamp'].weekday() >= 5]
    
    avg_weekday = sum(weekday_values) / len(weekday_values) if weekday_values else 0
    avg_weekend = sum(weekend_values) / len(weekend_values) if weekend_values else 0
    
    max_weekday = max(weekday_values) if weekday_values else 0
    max_weekend = max(weekend_values) if weekend_values else 0
    
    logger.info(f"Đã tạo xong {len(data_points)} điểm dữ liệu trong {num_days} ngày cho device_id: {device_id}")
    logger.info(f"Thống kê chi tiết:")
    logger.info(f"- Mùa: {season_name}")
    logger.info(f"- Ngày thường: {workdays} điểm, TB: {avg_weekday:.2f}W, Max: {max_weekday:.2f}W")
    logger.info(f"- Cuối tuần: {weekends} điểm, TB: {avg_weekend:.2f}W, Max: {max_weekend:.2f}W")
    logger.info(f"- Chênh lệch ngày thường/cuối tuần: {((avg_weekend / avg_weekday) - 1) * 100:.2f}%")
    
    return data_points

def save_to_database(device_id: str, data: List[float], timestamps: List[datetime], batch_size=1000):
    """
    Lưu dữ liệu vào database theo lô
    
    Args:
        device_id: ID của thiết bị
        data: List các giá trị dữ liệu
        timestamps: List các timestamp tương ứng
        batch_size: Kích thước mỗi lô
    """
    try:
        # Kết nối database
        engine = create_engine(DATABASE_URL)
        
        # Kiểm tra cấu trúc thực tế của bảng original_samples
        inspector = inspect(engine)
        columns = [column['name'] for column in inspector.get_columns('original_samples')]
        logger.info(f"Cột hiện có trong bảng original_samples: {columns}")
        
        # Tính số lượng lô
        num_batches = (len(data) + batch_size - 1) // batch_size
        
        with engine.connect() as conn:
            # Xử lý từng lô
            for i in range(num_batches):
                start_idx = i * batch_size
                end_idx = min((i + 1) * batch_size, len(data))
                
                # Chuẩn bị dữ liệu cho lô hiện tại
                batch_data = []
                for j in range(start_idx, end_idx):
                    # Tạo dữ liệu cơ bản
                    record = {
                        'device_id': device_id,
                        'value': float(data[j]),  # Chuyển đổi sang float để đảm bảo kiểu dữ liệu
                        'timestamp': timestamps[j]
                    }
                    
                    batch_data.append(record)
                
                try:
                    # Tạo câu SQL động dựa trên các cột có sẵn
                    column_names = ', '.join(batch_data[0].keys())
                    param_names = ', '.join([f":{name}" for name in batch_data[0].keys()])
                    
                    insert_sql = f"""
                        INSERT INTO original_samples ({column_names})
                        VALUES ({param_names})
                    """
                    
                    # Thực hiện insert
                    logger.info(f"Executing SQL: {insert_sql}")
                    conn.execute(text(insert_sql), batch_data)
                    conn.commit()
                    
                    logger.info(f"Đã lưu lô {i+1}/{num_batches}")
                    
                except Exception as e:
                    logger.error(f"Lỗi khi lưu điểm dữ liệu ở lô {i+1}/{num_batches}: {str(e)}")
                    conn.rollback()
                    raise
                    
    except Exception as e:
        logger.error(f"Lỗi khi lưu dữ liệu vào database: {str(e)}")
        raise

def ensure_device_exists(device_id: str, user_id=None):
    """
    Kiểm tra thiết bị đã tồn tại chưa, nếu chưa thì tạo mới
    
    Args:
        device_id: ID của thiết bị cần kiểm tra/tạo
        user_id: ID của người dùng sở hữu thiết bị (mặc định: None - chưa được claim)
        
    Returns:
        bool: True nếu thành công, False nếu thất bại
    """
    try:
        # Kết nối database
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            # Kiểm tra thiết bị đã tồn tại chưa
            result = conn.execute(
                text("SELECT id FROM devices WHERE device_id = :device_id"),
                {"device_id": device_id}
            ).fetchone()
            
            # Nếu thiết bị chưa tồn tại, tạo mới
            if not result:
                logger.info(f"Thiết bị {device_id} chưa tồn tại. Đang tạo thiết bị mới...")
                
                # Kiểm tra cấu trúc thực tế của bảng devices
                inspector = inspect(engine)
                columns = [column['name'] for column in inspector.get_columns('devices')]
                logger.info(f"Cột hiện có trong bảng devices: {columns}")
                
                # Tạo thiết bị mới với các cột cơ bản
                current_time = datetime.now()
                
                # Chỉ sử dụng các cột cơ bản và các cột thực sự tồn tại
                insert_data = {
                    'device_id': device_id
                }
                
                # Thêm user_id nếu được cung cấp và cột user_id tồn tại
                if user_id is not None and 'user_id' in columns:
                    insert_data['user_id'] = user_id
                
                # Thêm các cột khác nếu tồn tại
                if 'created_at' in columns:
                    insert_data['created_at'] = current_time
                
                # Tạo câu SQL động dựa trên các cột có sẵn
                column_names = ', '.join(insert_data.keys())
                param_names = ', '.join([f":{name}" for name in insert_data.keys()])
                
                insert_sql = f"""
                    INSERT INTO devices ({column_names})
                    VALUES ({param_names})
                """
                
                logger.info(f"Executing SQL: {insert_sql}")
                
                conn.execute(text(insert_sql), insert_data)
                conn.commit()
                logger.info(f"Đã tạo thiết bị mới với ID: {device_id}")
            else:
                logger.info(f"Thiết bị {device_id} đã tồn tại.")
                
            return True
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra/tạo thiết bị: {str(e)}")
        return False

def main():
    """
    Hàm chính của chương trình
    """
    # Tạo parser cho các tham số command line
    parser = argparse.ArgumentParser(description='Tạo dữ liệu giả lập cho template')
    parser.add_argument('--device-id', type=str, default='template_two', help='ID của thiết bị')
    parser.add_argument('--user-id', type=int, default=None, help='ID của người dùng (mặc định: None - chưa được claim)')
    parser.add_argument('--num-days', type=int, default=None, help='Số ngày dữ liệu cần tạo')
    parser.add_argument('--hour', type=int, default=None, help='Số giờ dữ liệu cần tạo')
    parser.add_argument('--start-date', type=str, help='Ngày bắt đầu (định dạng YYYY-MM-DD)')
    parser.add_argument('--no-save-db', action='store_true', help='Không lưu dữ liệu vào database')
    parser.add_argument('--season', type=str, choices=['summer', 'winter', 'spring', 'autumn'], 
                        help='Chỉ định mùa: summer (hè), winter (đông), spring (xuân), autumn (thu)')
    
    # Parse các tham số
    args = parser.parse_args()
    
    # Xác định số điểm dữ liệu
    points_per_hour = 12  # 5 phút/điểm
    if args.hour is not None:
        num_points = args.hour * points_per_hour
        num_days = None
    elif args.num_days is not None:
        num_days = args.num_days
        num_points = None
    else:
        num_days = 7
        num_points = None
    
    # Kiểm tra và chuyển đổi start_date
    start_date = None
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            logger.info(f"Sử dụng ngày bắt đầu: {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
        except ValueError as e:
            logger.error(f"Lỗi định dạng ngày bắt đầu: {str(e)}. Sử dụng thời gian hiện tại.")
    
    # Tạo dữ liệu template
    data_points = generate_template_data(
        num_days=num_days if num_points is None else 1,  # num_days chỉ dùng nếu không có num_points
        device_id=args.device_id, 
        start_date=start_date,
        season=args.season,
        num_points=num_points
    )
    
    # Lưu dữ liệu vào database nếu yêu cầu
    if not args.no_save_db:
        # Thiết lập kết nối database
        engine = setup_database()
        if not engine:
            logger.error("Không thể kết nối đến database! Kết thúc chương trình.")
            sys.exit(1)
            
        # Đảm bảo thiết bị tồn tại trước khi lưu dữ liệu
        if not ensure_device_exists(args.device_id, args.user_id):
            logger.error(f"Không thể đảm bảo thiết bị {args.device_id} tồn tại. Kết thúc chương trình.")
            sys.exit(1)
            
        # Lưu dữ liệu - giờ lưu trực tiếp giá trị value
        logger.info(f"Saving data to database for device_id: {args.device_id}, user_id: {args.user_id}")
        save_to_database(args.device_id, [point['value'] for point in data_points], [point['timestamp'] for point in data_points])
    else:
        logger.info(f"Đã bỏ qua việc lưu dữ liệu vào database cho device_id: {args.device_id} theo yêu cầu")
    
    # Thống kê nhanh về dữ liệu đã tạo
    workdays = sum(1 for point in data_points if point['timestamp'].weekday() < 5)
    weekends = len(data_points) - workdays
    logger.info(f"Thống kê: Đã tạo {len(data_points)} điểm dữ liệu, gồm {workdays} điểm cho ngày thường và {weekends} điểm cho cuối tuần")
    
    # Thống kê theo mùa
    month = data_points[0]['timestamp'].month
    if 3 <= month <= 4:
        season_name = "Xuân"
    elif 5 <= month <= 8:
        season_name = "Hè"
    elif 9 <= month <= 10:
        season_name = "Thu"
    else:
        season_name = "Đông"
    logger.info(f"Mùa: {season_name}")
    
    # Hoàn thành
    logger.info(f"Chương trình đã hoàn thành cho device_id: {args.device_id}")
    # Sửa lỗi so sánh None với int
    if (args.num_days is not None and args.num_days >= 30) or (args.hour is not None and args.hour >= 30*24):
        logger.info("Dữ liệu nhiều ngày đã được tạo thành công với các mẫu phức tạp theo mùa, ngày, tuần, và giờ!")
        logger.info("Bạn có thể phân tích dữ liệu để thấy sự khác biệt giữa các mẫu.")

if __name__ == "__main__":
    main()
