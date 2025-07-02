# Путь: /youtube_automation_bot/config/settings.py
# Описание: Настройки приложения из переменных окружения

import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Telegram
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    # Yandex
    YANDEX_SPEECHKIT_API_KEY = os.getenv("YANDEX_SPEECHKIT_API_KEY")
    YANDEX_SPEECHKIT_FOLDER_ID = os.getenv("YANDEX_SPEECHKIT_FOLDER_ID")
    YANDEX_DISK_TOKEN = os.getenv("YANDEX_DISK_TOKEN")
    
    # Claude AI
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    
    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///youtube_bot.db")
    
    # Paths
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
    
    # Whisper
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
    
    # Processing limits
    MAX_PARALLEL_PROJECTS = int(os.getenv("MAX_PARALLEL_PROJECTS", "3"))
    
    # API settings
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))

settings = Settings()