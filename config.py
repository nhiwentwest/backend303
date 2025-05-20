from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
from pathlib import Path
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lấy đường dẫn tuyệt đối đến file .env
env_path = Path(__file__).parent / '.env'
logger.info(f"Loading .env from: {env_path}")

# Load .env file
load_dotenv(dotenv_path=env_path, override=True)

# Log environment variables (ngoại trừ SECRET_KEY)
logger.info("Environment variables:")
logger.info(f"DATABASE_URL from env: {os.getenv('DATABASE_URL')}")
logger.info(f"ALGORITHM from env: {os.getenv('ALGORITHM')}")
logger.info(f"ACCESS_TOKEN_EXPIRE_MINUTES from env: {os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES')}")

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # MQTT Configuration cho Adafruit IO
    MQTT_HOST: str = "io.adafruit.com"
    MQTT_PORT: int = 8883  # Sử dụng 8883 cho SSL/TLS
    MQTT_USERNAME: str = ""  # Sẽ là ADAFRUIT_IO_USERNAME
    MQTT_PASSWORD: str = ""  # Sẽ là ADAFRUIT_IO_KEY
    MQTT_TOPIC: str = ""  # Mặc định là username/feeds/#
    MQTT_SSL: bool = True  # SSL flag
    
    # Adafruit IO thông tin
    ADAFRUIT_IO_USERNAME: str = ""
    ADAFRUIT_IO_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = True
        extra = "allow"  # Cho phép các biến môi trường phụ

try:
    settings = Settings()
    logger.info("Settings loaded successfully")
    logger.info(f"Final Database URL being used: {settings.DATABASE_URL}")
    logger.info(f"Final Algorithm being used: {settings.ALGORITHM}")
    logger.info(f"Final Token expire minutes: {settings.ACCESS_TOKEN_EXPIRE_MINUTES}")
except Exception as e:
    logger.error(f"Error loading settings: {str(e)}")
    raise 