# config/secure_settings.py
# Безопасная версия настроек с валидацией

import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

class Settings:
    def __init__(self):
        # Telegram - ВАЖНО: удалите токен из кода!
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        if not self.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN не установлен в .env файле")
        
        # Проверяем, что токен не хардкодный
        if self.TELEGRAM_TOKEN.startswith("7297610113"):
            logger.warning("⚠️ ВНИМАНИЕ: Используется токен из примера! Замените на свой!")
        
        # Yandex
        self.YANDEX_SPEECHKIT_API_KEY = os.getenv("YANDEX_SPEECHKIT_API_KEY")
        self.YANDEX_SPEECHKIT_FOLDER_ID = os.getenv("YANDEX_SPEECHKIT_FOLDER_ID")
        self.YANDEX_DISK_TOKEN = os.getenv("YANDEX_DISK_TOKEN")
        
        # Claude AI
        self.CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
        
        # Проверяем критичные ключи
        self._validate_critical_keys()
        
        # Redis
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        # Database
        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///youtube_bot.db")
        
        # Paths
        self.DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
        self.OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
        
        # Whisper
        self.WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large")  # Изменено на large
        
        # Processing limits
        self.MAX_PARALLEL_PROJECTS = int(os.getenv("MAX_PARALLEL_PROJECTS", "3"))
        
        # API settings
        self.API_HOST = os.getenv("API_HOST", "0.0.0.0")
        self.API_PORT = int(os.getenv("API_PORT", "8000"))
        
        # Target words для видео 80-100 минут
        self.TARGET_WORDS = int(os.getenv("TARGET_WORDS", "13500"))
        
    def _validate_critical_keys(self):
        """Проверяет наличие критичных ключей"""
        missing_keys = []
        
        critical_keys = {
            "YANDEX_SPEECHKIT_API_KEY": self.YANDEX_SPEECHKIT_API_KEY,
            "YANDEX_SPEECHKIT_FOLDER_ID": self.YANDEX_SPEECHKIT_FOLDER_ID,
            "YANDEX_DISK_TOKEN": self.YANDEX_DISK_TOKEN,
            "CLAUDE_API_KEY": self.CLAUDE_API_KEY
        }
        
        for key_name, key_value in critical_keys.items():
            if not key_value or key_value.startswith("ВСТАВЬТЕ_"):
                missing_keys.append(key_name)
        
        if missing_keys:
            logger.warning(f"⚠️ Отсутствуют ключи: {', '.join(missing_keys)}")
            logger.warning("Некоторые функции могут не работать!")
    
    def is_fully_configured(self) -> bool:
        """Проверяет, все ли настройки заполнены"""
        return all([
            self.TELEGRAM_TOKEN,
            self.YANDEX_SPEECHKIT_API_KEY,
            self.YANDEX_SPEECHKIT_FOLDER_ID,
            self.YANDEX_DISK_TOKEN,
            self.CLAUDE_API_KEY
        ])

# Создаем экземпляр настроек
settings = Settings()

# Экспортируем для обратной совместимости
__all__ = ['settings']