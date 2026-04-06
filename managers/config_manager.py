"""Менеджер системної конфігурації"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import asyncio

from models.db_system_config import SystemConfigDB
import config as default_config

logger = logging.getLogger(__name__)


class ConfigManager:
    """Менеджер для завантаження конфігів з БД з кешуванням"""
    
    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 хвилин
        self._lock = asyncio.Lock()
    
    async def get_config(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Отримати конфіг з БД або кешу.
        Якщо немає в БД - повертає дефолти з config.py
        """
        # Перевіряємо кеш
        if self._cache and self._is_cache_valid():
            logger.debug("Using cached config")
            return self._cache
        
        async with self._lock:
            # Подвійна перевірка після блокування
            if self._cache and self._is_cache_valid():
                return self._cache
            
            # Завантажуємо з БД
            try:
                stmt = select(SystemConfigDB).limit(1)
                result = await db.execute(stmt)
                db_config = result.scalar_one_or_none()
                
                if db_config:
                    config_dict = db_config.to_dict()
                    logger.debug("Loaded config from database")
                else:
                    # Якщо в БД нічого немає - створюємо дефолт
                    config_dict = self._get_default_config_dict()
                    logger.info("No config in database, using defaults")
                    
                    # Зберігаємо дефолт в БД
                    db_config = SystemConfigDB(**config_dict)
                    db.add(db_config)
                    await db.commit()
                    logger.info("Default config saved to database")
            except Exception as e:
                logger.error(f"Error loading config from database: {e}")
                config_dict = self._get_default_config_dict()
            
            self._cache = config_dict
            self._cache_time = datetime.utcnow()
            return config_dict
    
    async def update_config(self, db: AsyncSession, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Оновити конфіг в БД
        """
        async with self._lock:
            try:
                stmt = select(SystemConfigDB).limit(1)
                result = await db.execute(stmt)
                db_config = result.scalar_one_or_none()
                
                if not db_config:
                    # Якщо немає - створюємо все
                    defaults = self._get_default_config_dict()
                    defaults.update(updates)
                    db_config = SystemConfigDB(**defaults)
                else:
                    # Оновлюємо існуючий
                    for key, value in updates.items():
                        if hasattr(db_config, key):
                            setattr(db_config, key, value)
                
                db.add(db_config)
                await db.commit()
                
                # Інвалідуємо кеш
                self._cache = None
                self._cache_time = None
                
                logger.info(f"Config updated: {updates}")
                return db_config.to_dict()
                
            except Exception as e:
                logger.error(f"Error updating config: {e}")
                await db.rollback()
                raise
    
    def _is_cache_valid(self) -> bool:
        """Перевірити, чи кеш ще валідний"""
        if not self._cache_time:
            return False
        elapsed = (datetime.utcnow() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl_seconds
    
    def _get_default_config_dict(self) -> Dict[str, Any]:
        """Отримати дефолтні значення з config.py"""
        return {
            "access_token_expire_minutes": default_config.ACCESS_TOKEN_EXPIRE_MINUTES,
            "device_timeout_minutes": default_config.DEVICE_TIMEOUT_MINUTES,
            "registration_timeout_seconds": default_config.REGISTRATION_TIMEOUT_SECONDS,
            "device_cleanup_interval_seconds": default_config.DEVICE_CLEANUP_INTERVAL_SECONDS,
            "auth_cleanup_interval_seconds": default_config.AUTH_CLEANUP_INTERVAL_SECONDS,
            "device_not_returned_hours": default_config.DEVICE_NOT_RETURNED_HOURS,
            "allow_registration_without_login": default_config.ALLOW_REGISTRATION_WITHOUT_LOGIN,
        }
    
    def invalidate_cache(self):
        """Инвалідувати кеш"""
        self._cache = None
        self._cache_time = None


# Глобальний екземпляр менеджера конфігурації
config_manager = ConfigManager()
