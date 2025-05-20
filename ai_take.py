import pandas as pd
import numpy as np
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import json
import logging
import joblib
from fastapi import HTTPException, Query, Depends
from typing import List, Optional
import os
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score
from database import Session
from fastapi import FastAPI
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

# Cấu hình kết nối database
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Tạo URL từ các thành phần riêng lẻ
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Tạo engine và SessionLocal
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency để lấy session database
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Khởi tạo FastAPI app
app = FastAPI()

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_compressed_data(db, device_id):
    """
    Lấy dữ liệu từ bảng compressed_data_optimized
    """
    try:
        query = """
        SELECT 
            device_id,
            timestamp,
            compression_metadata,
            templates,
            encoded_stream,
            time_range
        FROM compressed_data_optimized
        WHERE device_id = :device_id
        ORDER BY timestamp
        """
        
        result = db.execute(text(query), {"device_id": device_id})
        records = result.fetchall()
        
        if not records:
            logger.warning(f"Không tìm thấy dữ liệu cho device_id: {device_id}")
            return []
            
        logger.info(f"Đã lấy {len(records)} bản ghi cho device_id: {device_id}")
        return records
        
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ database: {str(e)}")
        raise

def process_compressed_data(compressed_records):
    """
    Xử lý dữ liệu nén thành DataFrame
    """
    processed_data = []
    
    for record in compressed_records:
        try:
            device_id = record.device_id
            timestamp = record.timestamp
            
            # Giải nén templates và encoded_stream
            templates = record.templates if isinstance(record.templates, dict) else json.loads(record.templates)
            encoded_stream = record.encoded_stream if isinstance(record.encoded_stream, list) else json.loads(record.encoded_stream)
            
            # Xử lý từng block trong encoded_stream
            for block in encoded_stream:
                try:
                    template_id = str(block.get('template_id'))
                    if template_id not in templates:
                        logger.warning(f"Không tìm thấy template_id {template_id}")
                        continue
                        
                    template_data = templates[template_id]
                    
                    # Parse thời gian an toàn
                    try:
                        start_time = datetime.fromisoformat(block.get('start_time', '').replace('Z', '+00:00'))
                        end_time = datetime.fromisoformat(block.get('end_time', '').replace('Z', '+00:00'))
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Lỗi parse thời gian: {e}")
                        continue
                    
                    # Xử lý giá trị từ template
                    if isinstance(template_data, dict):
                        for key, values in template_data.items():
                            if isinstance(values, (list, np.ndarray)):
                                # Tính giá trị trung bình cho mỗi block
                                avg_value = np.mean(values)
                                
                                processed_data.append({
                                    'device_id': device_id,
                                    'timestamp': start_time,
                                    'value': avg_value,
                                    'template_id': template_id,
                                    'block_duration': (end_time - start_time).total_seconds() / 3600
                                })
                    elif isinstance(template_data, (list, np.ndarray)):
                        avg_value = np.mean(template_data)
                        processed_data.append({
                            'device_id': device_id,
                            'timestamp': start_time,
                            'value': avg_value,
                            'template_id': template_id,
                            'block_duration': (end_time - start_time).total_seconds() / 3600
                        })
                        
                except Exception as block_error:
                    logger.error(f"Lỗi xử lý block: {str(block_error)}")
                    continue
                    
        except Exception as record_error:
            logger.error(f"Lỗi xử lý record: {str(record_error)}")
            continue
    
    # Chuyển đổi thành DataFrame
    df = pd.DataFrame(processed_data)
    
    if df.empty:
        logger.warning("Không có dữ liệu sau khi xử lý")
        return df
        
    # Sắp xếp theo thời gian
    df = df.sort_values('timestamp')
    
    logger.info(f"Đã xử lý thành công {len(df)} mẫu dữ liệu")
    return df

def prepare_features(df):
    """
    Chuẩn bị các đặc trưng cho mô hình
    """
    if df.empty:
        return df
        
    try:
        # Thêm các đặc trưng thời gian
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['month'] = df['timestamp'].dt.month
        df['day'] = df['timestamp'].dt.day
        
        # Thêm đặc trưng mùa
        df['season'] = df['month'].apply(lambda x: (x%12 + 3)//3)
        
        # Thêm đặc trưng giờ trong ngày dạng sin/cos
        df['hour_sin'] = np.sin(2 * np.pi * df['hour']/24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour']/24)
        
        # Đặc trưng cho thời gian cao điểm
        df['is_peak_hour'] = df['hour'].apply(
            lambda x: 1 if (6 <= x <= 9) or (17 <= x <= 22) else 0
        )
        
        # Đặc trưng cho ngày cuối tuần
        df['is_weekend'] = df['day_of_week'].apply(
            lambda x: 1 if x >= 5 else 0
        )
        
        # Tính toán các đặc trưng thống kê
        df['rolling_mean_6h'] = df.groupby('device_id')['value'].rolling(
            window='6H', on='timestamp'
        ).mean().reset_index(0, drop=True)
        
        df['rolling_std_6h'] = df.groupby('device_id')['value'].rolling(
            window='6H', on='timestamp'
        ).std().reset_index(0, drop=True)
        
        # Thêm lag features
        df['lag_1h'] = df.groupby('device_id')['value'].shift(1)
        df['lag_24h'] = df.groupby('device_id')['value'].shift(24)
        
        # Thêm diff features
        df['diff_1h'] = df['value'] - df['lag_1h']
        
        # Xử lý missing values
        df = df.fillna(method='ffill')
        df = df.fillna(method='bfill')  # Cho những giá trị đầu tiên
        
        logger.info("Đã tạo xong các đặc trưng")
        return df
        
    except Exception as e:
        logger.error(f"Lỗi khi tạo đặc trưng: {str(e)}")
        raise

class PowerUsagePredictor:
    def __init__(self):
        self.model = LinearRegression()
        self.scaler = StandardScaler()
        self.model_version = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.training_history = []
        self.features = [
            'hour', 'day_of_week', 'month', 'day', 'season',
            'hour_sin', 'hour_cos', 'is_peak_hour', 'is_weekend',
            'rolling_mean_6h', 'rolling_std_6h', 'lag_1h', 'lag_24h',
            'diff_1h', 'block_duration'
        ]
    
    def validate_data(self, df):
        """Kiểm tra dữ liệu trước khi huấn luyện"""
        if df.empty:
            raise ValueError("DataFrame rỗng")
            
        missing_features = [f for f in self.features if f not in df.columns]
        if missing_features:
            raise ValueError(f"Thiếu các đặc trưng: {missing_features}")
            
        if df['value'].isnull().any():
            raise ValueError("Có giá trị null trong cột value")
    
    def prepare_data(self, df):
        """Chuẩn bị dữ liệu cho mô hình"""
        self.validate_data(df)
        
        X = df[self.features]
        y = df['value']
        
        # Chia dữ liệu
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Chuẩn hóa features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        return X_train_scaled, X_test_scaled, y_train, y_test
    
    def train(self, df):
        """Huấn luyện mô hình"""
        try:
            # Chuẩn bị dữ liệu
            X_train_scaled, X_test_scaled, y_train, y_test = self.prepare_data(df)
            
            # Huấn luyện mô hình
            self.model.fit(X_train_scaled, y_train)
            
            # Đánh giá mô hình
            train_pred = self.model.predict(X_train_scaled)
            test_pred = self.model.predict(X_test_scaled)
            
            metrics = {
                'train_r2': r2_score(y_train, train_pred),
                'test_r2': r2_score(y_test, test_pred),
                'train_rmse': np.sqrt(mean_squared_error(y_train, train_pred)),
                'test_rmse': np.sqrt(mean_squared_error(y_test, test_pred)),
                'coefficients': dict(zip(self.features, self.model.coef_)),
                'intercept': float(self.model.intercept_)
            }
            
            # Lưu lịch sử huấn luyện
            self.training_history.append({
                'timestamp': datetime.now(),
                'metrics': metrics
            })
            
            logger.info(f"Huấn luyện mô hình thành công. Test R2: {metrics['test_r2']:.4f}")
            return metrics
            
        except Exception as e:
            logger.error(f"Lỗi khi huấn luyện mô hình: {str(e)}")
            raise
    
    def predict(self, new_data):
        """Dự đoán với dữ liệu mới"""
        try:
            X_new = new_data[self.features]
            X_new_scaled = self.scaler.transform(X_new)
            predictions = self.model.predict(X_new_scaled)
            return predictions
        except Exception as e:
            logger.error(f"Lỗi khi dự đoán: {str(e)}")
            raise
            
    def save_model(self, path):
        """Lưu mô hình và scaler"""
        try:
            # Tạo thư mục nếu chưa tồn tại
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            model_info = {
                'model': self.model,
                'scaler': self.scaler,
                'features': self.features,
                'version': self.model_version,
                'training_history': self.training_history
            }
            
            joblib.dump(model_info, path)
            logger.info(f"Đã lưu mô hình vào {path}")
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu mô hình: {str(e)}")
            raise
            
    def load_model(self, path):
        """Tải mô hình đã lưu"""
        try:
            model_info = joblib.load(path)
            self.model = model_info['model']
            self.scaler = model_info['scaler']
            self.features = model_info['features']
            self.model_version = model_info['version']
            self.training_history = model_info.get('training_history', [])
            
            logger.info(f"Đã tải mô hình từ {path}")
            
        except Exception as e:
            logger.error(f"Lỗi khi tải mô hình: {str(e)}")
            raise

@app.post("/train-power-model/{device_id}")
def train_power_model(
    device_id: str,
    db: Session = Depends(get_db)
):
    try:
        logger.info(f"Bắt đầu huấn luyện mô hình cho device {device_id}")
        
        # Lấy dữ liệu từ database
        compressed_records = get_compressed_data(db, device_id)
        
        if not compressed_records:
            raise HTTPException(
                status_code=404,
                detail=f"Không tìm thấy dữ liệu cho device {device_id}"
            )
        
        # Xử lý dữ liệu nén
        df = process_compressed_data(compressed_records)
        
        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="Không thể xử lý dữ liệu nén"
            )
        
        # Chuẩn bị features
        df = prepare_features(df)
        
        # Khởi tạo và huấn luyện mô hình
        predictor = PowerUsagePredictor()
        metrics = predictor.train(df)
        
        # Dự đoán cho 24h tiếp theo
        last_timestamp = df['timestamp'].max()
        future_data = pd.DataFrame()
        
        # Tạo dữ liệu cho 24h tiếp theo
        future_timestamps = pd.date_range(
            start=last_timestamp,
            periods=24,
            freq='H'
        )
        
        future_data['timestamp'] = future_timestamps
        future_data = prepare_features(future_data)
        
        predictions = predictor.predict(future_data)
        
        # Lưu mô hình
        model_path = f"models/power_predictor_{device_id}.joblib"
        predictor.save_model(model_path)
        
        return {
            "device_id": device_id,
            "model_performance": metrics,
            "future_predictions": [float(p) for p in predictions],
            "prediction_timestamps": [ts.isoformat() for ts in future_timestamps],
            "model_info": {
                "version": predictor.model_version,
                "features_used": predictor.features,
                "training_size": len(df),
                "model_path": model_path
            }
        }
        
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Lỗi không mong đợi: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi huấn luyện mô hình: {str(e)}"
        )

@app.post("/update-power-model/{device_id}")
def update_power_model(
    device_id: str,
    db: Session = Depends(get_db)
):
    try:
        # Kiểm tra xem mô hình cũ có tồn tại không
        model_path = f"models/power_predictor_{device_id}.joblib"
        predictor = PowerUsagePredictor()
        
        try:
            predictor.load_model(model_path)
            logger.info(f"Đã tải mô hình cũ cho device {device_id}")
        except:
            logger.warning(f"Không tìm thấy mô hình cũ cho device {device_id}")
        
        # Lấy dữ liệu mới và cập nhật mô hình
        return train_power_model(device_id, db)
        
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mô hình: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.get("/get-predictions/{device_id}")
def get_predictions(
    device_id: str,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    try:
        # Tải mô hình đã lưu
        model_path = f"models/power_predictor_{device_id}.joblib"
        predictor = PowerUsagePredictor()
        
        try:
            predictor.load_model(model_path)
        except:
            raise HTTPException(
                status_code=404,
                detail=f"Không tìm thấy mô hình cho device {device_id}"
            )
        
        # Lấy thời điểm cuối cùng từ dữ liệu
        compressed_records = get_compressed_data(db, device_id)
        df = process_compressed_data(compressed_records)
        
        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="Không có dữ liệu để dự đoán"
            )
        
        last_timestamp = df['timestamp'].max()
        
        # Tạo dữ liệu cho khoảng thời gian yêu cầu
        future_timestamps = pd.date_range(
            start=last_timestamp,
            periods=hours,
            freq='H'
        )
        
        future_data = pd.DataFrame({'timestamp': future_timestamps})
        future_data = prepare_features(future_data)
        
        # Dự đoán
        predictions = predictor.predict(future_data)
        
        return {
            "device_id": device_id,
            "predictions": [float(p) for p in predictions],
            "timestamps": [ts.isoformat() for ts in future_timestamps]
        }
        
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Lỗi khi lấy dự đoán: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.get("/evaluate-model/{device_id}")
def evaluate_model(device_id: str, db: Session = Depends(get_db)):
    try:
        # Tải mô hình
        model_path = f"models/power_predictor_{device_id}.joblib"
        predictor = PowerUsagePredictor()
        
        try:
            predictor.load_model(model_path)
        except:
            raise HTTPException(
                status_code=404,
                detail=f"Không tìm thấy mô hình cho device {device_id}"
            )
        
        # Lấy dữ liệu gần đây để đánh giá
        compressed_records = get_compressed_data(db, device_id)
        df = process_compressed_data(compressed_records)
        
        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="Không có dữ liệu để đánh giá"
            )
        
        # Chuẩn bị features
        df = prepare_features(df)
        
        # Đánh giá mô hình
        X = df[predictor.features]
        y = df['value']
        
        X_scaled = predictor.scaler.transform(X)
        predictions = predictor.model.predict(X_scaled)
        
        metrics = {
            'r2_score': r2_score(y, predictions),
            'rmse': np.sqrt(mean_squared_error(y, predictions)),
            'model_version': predictor.model_version,
            'training_history': predictor.training_history
        }
        
        return {
            "device_id": device_id,
            "evaluation_metrics": metrics
        }
        
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Lỗi khi đánh giá mô hình: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )