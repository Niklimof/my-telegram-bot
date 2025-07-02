# Путь: /youtube_automation_bot/workers/tasks/text_tasks.py
# Описание: Celery задачи для обработки текста

from celery import shared_task
from core.pipeline.text_pipeline import TextPipeline
from database.crud import update_project, add_log, get_project, get_plan
from config.settings import settings
from interfaces.telegram_bot.bot import notify_progress
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_text_pipeline(self, project_id: str):
    """Запускает pipeline обработки текста"""
    
    try:
        # Получаем данные проекта
        project = get_project(project_id)
        plan = get_plan(project.plan_id)
        
        # Обновляем статус
        update_project(project_id, {
            "status": "processing",
            "phase": 1,
            "started_at": datetime.now()
        })
        
        # Создаем pipeline
        config = {
            "whisper_model": project.settings.whisper_model,
            "claude_api_key": settings.CLAUDE_API_KEY,
            "speechkit_api_key": settings.YANDEX_SPEECHKIT_API_KEY,
            "speechkit_folder_id": settings.YANDEX_SPEECHKIT_FOLDER_ID,
            "yandex_disk_token": settings.YANDEX_DISK_TOKEN
        }
        
        pipeline = TextPipeline(config)
        
        # Коллбеки для обновления прогресса
        async def update_progress(message: str):
            add_log(project_id, "info", "pipeline", message)
            
            # Отправляем уведомление в Telegram
            if project.telegram_chat_id:
                await notify_progress(project.telegram_chat_id, project_id, message)
        
        callbacks = {
            "download_start": update_progress,
            "download_complete": update_progress,
            "transcribe_start": update_progress,
            "transcribe_complete": update_progress,
            "process_start": update_progress,
            "process_complete": update_progress,
            "speech_start": update_progress,
            "speech_complete": update_progress,
            "upload_start": update_progress,
            "upload_complete": update_progress,
            "pipeline_complete": update_progress,
            "pipeline_error": update_progress
        }
        
        # Запускаем pipeline
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        results = loop.run_until_complete(
            pipeline.process(
                project_id=project_id,
                youtube_url=project.youtube_url,
                plan=plan.__dict__,
                callbacks=callbacks
            )
        )
        
        # Обновляем проект с результатами
        update_project(project_id, {
            "status": "completed",
            "completed_at": datetime.now(),
            "transcription_text": results["steps"]["transcription"]["text"],
            "transcription_word_count": results["steps"]["transcription"]["word_count"],
            "processed_text": results["steps"]["text_processing"]["text"],
            "processed_word_count": results["steps"]["text_processing"]["word_count"],
            "speech_chunks": results["steps"]["speech_generation"]["audio_files"],
            "speech_duration": results["steps"]["speech_generation"]["total_duration"],
            "yandex_folder_url": results["yandex_folder_url"]
        })
        
        add_log(project_id, "info", "pipeline", 
                f"Обработка завершена успешно за {results['processing_time']/60:.1f} минут")
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка в pipeline проекта {project_id}: {str(e)}")
        
        update_project(project_id, {
            "status": "failed",
            "error_message": str(e)
        })
        
        add_log(project_id, "error", "pipeline", f"Критическая ошибка: {str(e)}")
        
        # Повторная попытка
        raise self.retry(exc=e, countdown=300)  # Повтор через 5 минут