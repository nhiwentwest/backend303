from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from config import settings
import models
from database import get_db
import logging
from pydantic import BaseModel
import os
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cấu hình OAuth2
ALGORITHM = settings.ALGORITHM
SECRET_KEY = settings.SECRET_KEY
ACCESS_TOKEN_EXPIRE_DAYS = 30
COOKIE_NAME = "auth_token"

# Cấu hình OAuth2
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login", 
    auto_error=False  # Quan trọng: không tự động gây lỗi khi không tìm thấy token
)

# Cài đặt password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Cài đặt cookie
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 ngày
COOKIE_PATH = "/"
COOKIE_DOMAIN = None
COOKIE_SECURE = False  # Đặt thành False để cho phép localhost
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = "lax"

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

def verify_password(plain_password, hashed_password):
    logger.info(f"Verifying password for hash: {hashed_password[:20]}...")
    result = pwd_context.verify(plain_password, hashed_password)
    logger.info(f"Password verification result: {result}")
    return result

def get_password_hash(password):
    logger.info("Generating password hash...")
    hashed = pwd_context.hash(password)
    logger.info(f"Generated hash: {hashed[:20]}...")
    return hashed

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        
    to_encode.update({"exp": expire})
    
    # In thông tin token sẽ được tạo để debug
    logger.info(f"Creating token with payload: {to_encode}")
    logger.info(f"Using SECRET_KEY (first 10 chars): {SECRET_KEY[:10]}...")
    logger.info(f"Using ALGORITHM: {ALGORITHM}")
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    # Log token để debug
    logger.info(f"Token created (first 20 chars): {encoded_jwt[:20]}...")
    
    return encoded_jwt

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Xác thực người dùng hiện tại từ token JWT
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực người dùng",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # DEBUG: In thông tin token và request
    logger.info("=== BEGIN AUTH DEBUG ===")
    
    # Log trực tiếp headers từ request
    if request and hasattr(request, 'headers'):
        logger.info(f"ALL REQUEST HEADERS: {dict(request.headers)}")
    
    if token and token != "undefined":
        logger.info(f"Token từ oauth2_scheme: {token[:20]}...")
    else:
        logger.info("Không có token từ oauth2_scheme hoặc token không hợp lệ")
    
    if request:
        auth_header = request.headers.get("authorization", "")
        logger.info(f"Auth header: {auth_header[:30] if auth_header else 'None'}")
        
        cookie_token = request.cookies.get(COOKIE_NAME, "")
        logger.info(f"Cookie token: {cookie_token[:20] if cookie_token else 'None'}")
    
    # Thử lấy token từ nhiều nguồn
    final_token = None
    token_source = None
    
    # 1. Từ OAuth2
    if token and token != "undefined":
        logger.info("Sử dụng token từ oauth2_scheme")
        final_token = token
        token_source = "oauth2_scheme"
    # 2. Từ header Authorization nếu có request
    elif request and request.headers.get("authorization"):
        auth_header = request.headers.get("authorization", "")
        logger.info(f"Tìm thấy Authorization header: {auth_header[:30] if auth_header else 'None'}")
        
        if auth_header and auth_header.startswith("Bearer "):
            final_token = auth_header.replace("Bearer ", "").strip()
            logger.info(f"Sử dụng token từ Authorization header: {final_token[:20]}...")
            token_source = "auth_header"
    # 3. Từ cookie
    elif request and COOKIE_NAME in request.cookies:
        cookie_token = request.cookies.get(COOKIE_NAME, "")
        logger.info(f"Sử dụng token từ cookie: {cookie_token[:20]}...")
        final_token = cookie_token
        token_source = "cookie"
    
    if not final_token:
        logger.error("Không tìm thấy token từ bất kỳ nguồn nào")
        logger.info("=== END AUTH DEBUG ===")
        raise credentials_exception
    
    # Thêm debug: Log full token để kiểm tra
    logger.info(f"FULL TOKEN ({token_source}): {final_token}")
    
    # Đã có token, giải mã để xác thực
    try:
        # Kiểm tra xem SECRET_KEY có đúng không
        logger.info(f"Giải mã token với SECRET_KEY (first 10): {SECRET_KEY[:10]}...")
        logger.info(f"Algorithm: {ALGORITHM}")
        
        # Trước khi decode, kiểm tra định dạng token
        parts = final_token.split('.')
        if len(parts) != 3:
            logger.error(f"Token không đúng định dạng JWT (cần 3 phần, tìm thấy {len(parts)})")
            raise JWTError("Invalid token format")
        
        # Thử decode token
        try:
            # Thử giải mã trước với verify=False để xem cấu trúc
            payload_unverified = jwt.decode(final_token, key=None, options={"verify_signature": False})
            logger.info(f"Token payload (unverified): {payload_unverified}")
        except Exception as e:
            logger.error(f"Lỗi khi decode token không xác minh: {str(e)}")
        
        # Decode có xác minh chữ ký
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        
        logger.info(f"Decoded payload (verified): {payload}")
        
        if not username:
            logger.error("Token không chứa trường 'sub'")
            logger.info("=== END AUTH DEBUG ===")
            raise credentials_exception
        
        # Tìm user trong database
        user = db.query(models.User).filter(models.User.username == username).first()
        
        if not user:
            logger.error(f"Không tìm thấy user: {username}")
            logger.info("=== END AUTH DEBUG ===")
            raise credentials_exception
        
        logger.info(f"Xác thực thành công cho user: {user.username}")
        logger.info("=== END AUTH DEBUG ===")
        return user
    except JWTError as e:
        logger.error(f"Lỗi giải mã JWT: {str(e)}")
        logger.info("=== END AUTH DEBUG ===")
        # Thêm thử nghiệm với các SECRET_KEY khác để debug
        try:
            alt_keys = [
                "your_secret_key_here",
                "secret",
                "your-256-bit-secret"
            ]
            for key in alt_keys:
                try:
                    alt_payload = jwt.decode(final_token, key, algorithms=[ALGORITHM])
                    logger.error(f"Token hợp lệ với key thay thế: {key[:5]}... - {alt_payload}")
                except:
                    pass
        except:
            pass
        raise credentials_exception

def set_auth_cookie(response: Response, token: str):
    """
    Đặt cookie xác thực
    """
    logger.info(f"Setting auth cookie: {token[:20]}...")
    
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        expires=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=False,
        path="/"
    )
    
    # Log cho debug
    logger.info(f"Set auth cookie: {COOKIE_NAME}={token[:10]}...")

def clear_auth_cookie(response):
    """
    Xóa cookie xác thực
    
    Args:
        response: FastAPI response object
    """
    try:
        response.delete_cookie(
            key=COOKIE_NAME,
            path="/"
        )
        logger.info("Đã xóa cookie xác thực")
    except Exception as e:
        logger.error(f"Lỗi khi xóa cookie: {str(e)}")
        raise 