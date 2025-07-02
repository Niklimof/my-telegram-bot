# Путь: /youtube_automation_bot/init_database.py
# Описание: Скрипт инициализации базы данных с примерами планов

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, PlanV2, ProcessingSettings
from config.settings import settings
import json

def init_database():
    """Инициализирует базу данных и создает примеры данных"""
    
    # Создаем engine
    engine = create_engine(settings.DATABASE_URL)
    
    # Создаем таблицы
    Base.metadata.create_all(bind=engine)
    
    # Создаем сессию
    Session = sessionmaker(bind=engine)
    session = Session()
    
    print("✅ База данных создана")
    
    # Проверяем, есть ли уже данные
    existing_settings = session.query(ProcessingSettings).filter_by(is_default=True).first()
    if existing_settings:
        print("ℹ️ База данных уже содержит данные")
        return
    
    # Создаем настройки по умолчанию
    default_settings = ProcessingSettings(
        name="Стандартные настройки",
        is_default=True,
        whisper_model="medium",
        whisper_language="ru",
        speechkit_voice="alena",
        speechkit_speed=1.0,
        speechkit_emotion="neutral",
        claude_model="claude-3-sonnet-20240229",
        claude_temperature=0.7,
        video_settings={
            "photos_folder": "/VideoAutomation/Photos",
            "photos_count": 50,
            "photo_duration": 10,
            "zoom_effect": {"min": 100, "max": 120},
            "subtitle_settings": {
                "font": "Arial",
                "size": 24,
                "color": "#FFFFFF",
                "position": "bottom"
            }
        }
    )
    session.add(default_settings)
    print("✅ Создали настройки по умолчанию")
    
    # Создаем примеры планов
    plans = [
        {
            "name": "Базовая обработка",
            "description": "Стандартный план для большинства видео",
            "text_steps": [
                {
                    "type": "extract_audio",
                    "params": {"format": "mp3"}
                },
                {
                    "type": "transcribe",
                    "params": {
                        "language": "ru",
                        "model": "medium"
                    }
                },
                {
                    "type": "process_with_claude",
                    "params": {
                        "prompt": "Перепиши этот текст в более динамичном и энергичном стиле. Сократи паузы, добавь эмоций, сделай речь более живой и захватывающей. Сохрани все важные факты и основной смысл. Расширь текст добавляя интересные детали, примеры и объяснения. Целевой объем - примерно 20000 слов.",
                        "model": "claude-3-sonnet-20240229",
                        "temperature": 0.7
                    }
                },
                {
                    "type": "generate_speech",
                    "params": {
                        "voice": "alena",
                        "emotion": "neutral",
                        "speed": 1.0
                    }
                }
            ],
            "video_steps": [],  # Для фазы 2
            "default_prompt": "Перепиши текст в динамичном стиле",
            "default_voice": "alena",
            "is_active": True,
            "modules_enabled": ["text"]
        },
        {
            "name": "Образовательный контент",
            "description": "Для создания обучающих видео",
            "text_steps": [
                {
                    "type": "extract_audio",
                    "params": {"format": "mp3"}
                },
                {
                    "type": "transcribe",
                    "params": {
                        "language": "ru",
                        "model": "medium"
                    }
                },
                {
                    "type": "process_with_claude",
                    "params": {
                        "prompt": "Адаптируй этот текст для образовательного контента. Структурируй информацию логично, выдели ключевые моменты, добавь примеры, аналогии и объяснения для лучшего понимания. Раздели на тематические блоки. Добавь практические советы и выводы. Целевой объем - 20000 слов.",
                        "model": "claude-3-sonnet-20240229",
                        "temperature": 0.5
                    }
                },
                {
                    "type": "generate_speech",
                    "params": {
                        "voice": "alena",
                        "emotion": "neutral",
                        "speed": 0.95
                    }
                }
            ],
            "video_steps": [],
            "default_prompt": "Адаптируй для образовательного контента",
            "default_voice": "alena",
            "is_active": True,
            "modules_enabled": ["text"]
        },
        {
            "name": "Сторителлинг",
            "description": "Превращает контент в увлекательную историю",
            "text_steps": [
                {
                    "type": "extract_audio",
                    "params": {"format": "mp3"}
                },
                {
                    "type": "transcribe",
                    "params": {
                        "language": "ru",
                        "model": "medium"
                    }
                },
                {
                    "type": "process_with_claude",
                    "params": {
                        "prompt": "Перепиши этот текст в формате захватывающей истории. Добавь интригу, эмоциональные моменты, сделай повествование более личным и вовлекающим. Используй приемы сторителлинга: завязка, развитие, кульминация. Добавь диалоги, описания, детали. Расширь до 20000 слов.",
                        "model": "claude-3-sonnet-20240229",
                        "temperature": 0.8
                    }
                },
                {
                    "type": "generate_speech",
                    "params": {
                        "voice": "alena",
                        "emotion": "good",
                        "speed": 1.05
                    }
                }
            ],
            "video_steps": [],
            "default_prompt": "Превратить в захватывающую историю",
            "default_voice": "alena",
            "is_active": True,
            "modules_enabled": ["text"]
        }
    ]
    
    # Добавляем планы
    for plan_data in plans:
        plan = PlanV2(**plan_data)
        session.add(plan)
        print(f"✅ Создали план: {plan_data['name']}")
    
    # Сохраняем изменения
    session.commit()
    session.close()
    
    print("\n✅ Инициализация завершена!")
    print("\nДоступные планы:")
    for i, plan in enumerate(plans, 1):
        print(f"{i}. {plan['name']} - {plan['description']}")

if __name__ == "__main__":
    init_database()