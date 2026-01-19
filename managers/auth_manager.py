"""Менеджер автентифікації та сесій"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.db_user import UserDB

logger = logging.getLogger(__name__)

# Конфігурація
SECRET_KEY = "your-secret-key-here-change-in-production"  # Змініть на безпечний ключ
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Використовуємо pbkdf2_sha256 щоб уникнути проблем з bcrypt
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],  # pbkdf2_sha256 буде першим за замовчуванням
    deprecated="auto"
)


class AuthManager:
    def __init__(self):
        self.active_sessions: Dict[str, dict] = {}  # token -> user_data
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Перевірка пароля"""
        try:
            # Перевіряємо з pbkdf2_sha256 (або іншим алгоритмом)
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.warning(f"Password verification failed: {e}")
            return False
    
    def get_password_hash(self, password: str) -> str:
        """Хешування пароля"""
        # Використовуємо pbkdf2_sha256 за замовчуванням
        return pwd_context.hash(password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def decode_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            return None
    
    async def authenticate_user(self, db: AsyncSession, username: str, password: str):
        result = await db.execute(
            select(UserDB).where(UserDB.username == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User {username} not found")
            return None
        
        # Додаткове логування для діагностики
        logger.info(f"Authenticating user: {username}")
        logger.info(f"Password hash in DB: {user.password_hash[:50]}...")
        
        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Password verification failed for user: {username}")
            return None
        
        if not user.is_active:
            logger.warning(f"User {username} is not active")
            return None
        
        logger.info(f"User {username} authenticated successfully")
        return user
    
    def add_session(self, token: str, user_data: dict):
        self.active_sessions[token] = {
            "user": user_data,
            "created_at": datetime.now()
        }
    
    def remove_session(self, token: str):
        self.active_sessions.pop(token, None)
    
    def get_user_from_token(self, token: str) -> Optional[dict]:
        if token in self.active_sessions:
            return self.active_sessions[token]["user"]
        return None
    
    def cleanup_expired_sessions(self):
        expired = []
        for token, session in self.active_sessions.items():
            if datetime.now() - session["created_at"] > timedelta(hours=24):
                expired.append(token)
        
        for token in expired:
            self.active_sessions.pop(token, None)


auth_manager = AuthManager()