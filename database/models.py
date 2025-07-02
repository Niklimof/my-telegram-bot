# Путь: /youtube_automation_bot/database/models.py
# Описание: Модели базы данных SQLAlchemy

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class PlanV2(Base):
    __tablename__ = "plans_v2"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text)
    
    # Шаги обработки
    text_steps = Column(JSON)  # Шаги фазы 1 (обязательные)
    video_steps = Column(JSON)  # Шаги фазы 2 (опциональные)
    
    # Настройки по умолчанию
    default_prompt = Column(Text)
    default_voice = Column(String, default="alena")
    default_video_settings = Column(JSON)
    
    is_active = Column(Boolean, default=True)
    modules_enabled = Column(JSON, default=["text"])
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    projects = relationship("ProjectV2", back_populates="plan")

class ProcessingSettings(Base):
    __tablename__ = "processing_settings_v2"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    # Whisper настройки
    whisper_model = Column(String, default="medium")
    whisper_language = Column(String, default="ru")
    
    # SpeechKit настройки
    speechkit_voice = Column(String, default="alena")
    speechkit_speed = Column(Float, default=1.0)
    speechkit_emotion = Column(String, default="neutral")
    
    # Claude настройки
    claude_model = Column(String, default="claude-3-sonnet-20240229")
    claude_temperature = Column(Float, default=0.7)
    
    # Видео настройки (для фазы 2)
    video_settings = Column(JSON)
    
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    projects = relationship("ProjectV2", back_populates="settings")

class ProjectV2(Base):
    __tablename__ = "projects_v2"
    
    id = Column(String, primary_key=True, index=True)
    
    # Исходные данные
    youtube_url = Column(String)
    original_video_path = Column(String)
    original_duration = Column(Float)
    
    # Результаты транскрибации
    transcription_text = Column(Text)
    transcription_word_count = Column(Integer)
    
    # Результаты обработки текста
    processed_text = Column(Text)
    processed_word_count = Column(Integer)
    processing_prompt = Column(Text)
    
    # Результаты озвучки
    speech_chunks = Column(JSON)
    speech_duration = Column(Float)
    speech_voice = Column(String)
    
    # Настройки монтажа (для фазы 2)
    video_settings = Column(JSON)
    
    # Результаты монтажа (для фазы 2)
    final_video_path = Column(String)
    final_video_duration = Column(Float)
    
    # Яндекс.Диск
    yandex_folder_url = Column(String)
    
    # Связи
    plan_id = Column(Integer, ForeignKey("plans_v2.id"))
    settings_id = Column(Integer, ForeignKey("processing_settings_v2.id"))
    
    # Telegram
    telegram_user_id = Column(Integer)
    telegram_chat_id = Column(Integer)
    
    # Статус и метаданные
    status = Column(String, default="created")
    phase = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    # Celery
    task_id = Column(String)
    
    # Связи
    plan = relationship("PlanV2", back_populates="projects")
    settings = relationship("ProcessingSettings", back_populates="projects")
    logs = relationship("ProcessingLog", back_populates="project")

class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects_v2.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String)
    step = Column(String)
    message = Column(Text)
    details = Column(JSON)
    
    project = relationship("ProjectV2", back_populates="logs")