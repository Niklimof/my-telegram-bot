# workers/tasks/updated_text_tasks.py
# Обновленные Celery задачи с двойной обработкой Claude

from celery import shared_task
from core.pipeline.updated_text_pipeline import UpdatedTextPipeline
from database.crud import update_project, add_log, get_project, get_plan
from config.secure_settings import settings
from interfaces.telegram_bot.improved_bot import notify_progress
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_text_pipeline(self, project_id: str):
    """Запускает pipeline обработки текста с двойной обработкой Claude"""
    
    try:
        # Получаем данные проекта
        project = get_project(project_id)
        if not project:
            raise ValueError(f"Проект {project_id} не найден")
            
        plan = get_plan(project.plan_id)
        if not plan:
            raise ValueError(f"План {project.plan_id} не найден")
        
        # Обновляем статус
        update_project(project_id, {
            "status": "processing",
            "phase": 1,
            "started_at": datetime.now()
        })
        
        # Проверяем конфигурацию
        if not settings.is_fully_configured():
            raise ValueError("Не все API ключи настроены. Проверьте .env файл")
        
        # Создаем pipeline
        config = {
            "whisper_model": project.settings.whisper_model,
            "claude_api_key": settings.CLAUDE_API_KEY,
            "speechkit_api_key": settings.YANDEX_SPEECHKIT_API_KEY,
            "speechkit_folder_id": settings.YANDEX_SPEECHKIT_FOLDER_ID,
            "yandex_disk_token": settings.YANDEX_DISK_TOKEN
        }
        
        pipeline = UpdatedTextPipeline(config)
        
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
            "claude_plan_start": update_progress,
            "claude_story_start": update_progress,
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
        update_data = {
            "status": "completed",
            "completed_at": datetime.now(),
            "transcription_text": results["steps"]["transcription"]["text"],
            "transcription_word_count": results["steps"]["transcription"]["word_count"],
            "processed_text": results["steps"]["text_processing"]["story"],
            "processed_word_count": results["steps"]["text_processing"]["word_count"],
            "processing_prompt": results["steps"]["text_processing"]["plan"][:500] + "...",
            "speech_chunks": results["steps"]["speech_generation"]["audio_files"],
            "speech_duration": results["steps"]["speech_generation"]["total_duration"],
            "speech_voice": results["steps"]["speech_generation"]["voice"],
            "yandex_folder_url": results["yandex_folder_url"]
        }
        
        update_project(project_id, update_data)
        
        add_log(project_id, "info", "pipeline", 
                f"✅ Обработка завершена успешно за {results['processing_time']/60:.1f} минут")
        
        # Отправляем финальное уведомление
        if project.telegram_chat_id:
            loop.run_until_complete(
                notify_progress(
                    project.telegram_chat_id, 
                    project_id,
                    f"🎉 Ваш рассказ готов!\n"
                    f"📁 Скачать: {results['yandex_folder_url']}\n"
                    f"⏱ Длительность: ~{results['steps']['speech_generation']['total_duration']/60:.1f} минут\n"
                    f"📝 Слов: {results['steps']['text_processing']['word_count']}"
                )
            )
        
        return results
        
    except Exception as e:
        logger.error(f"Ошибка в pipeline проекта {project_id}: {str(e)}")
        
        update_project(project_id, {
            "status": "failed",
            "error_message": str(e),
            "completed_at": datetime.now()
        })
        
        add_log(project_id, "error", "pipeline", f"❌ Критическая ошибка: {str(e)}")
        
        # Уведомляем пользователя об ошибке
        try:
            project = get_project(project_id)
            if project and project.telegram_chat_id:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    notify_progress(
                        project.telegram_chat_id,
                        project_id,
                        f"❌ Произошла ошибка при обработке.\n"
                        f"Попробуем еще раз через 5 минут."
                    )
                )
        except:
            pass
        
        # Повторная попытка
        raise self.retry(exc=e, countdown=300)  # Повтор через 5 минут

@shared_task
def cleanup_old_files(days_to_keep: int = 7):
    """Очищает старые файлы проектов"""
    import os
    import shutil
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    # Очищаем папку downloads
    downloads_dir = settings.DOWNLOAD_DIR
    if os.path.exists(downloads_dir):
        for folder in os.listdir(downloads_dir):
            folder_path = os.path.join(downloads_dir, folder)
            if os.path.isdir(folder_path):
                # Проверяем дату создания
                folder_time = datetime.fromtimestamp(os.path.getctime(folder_path))
                if folder_time < cutoff_date:
                    logger.info(f"Удаляем старую папку: {folder_path}")
                    shutil.rmtree(folder_path)
    
    # Очищаем папку outputs
    outputs_dir = settings.OUTPUT_DIR
    if os.path.exists(outputs_dir):
        for folder in os.listdir(outputs_dir):
            folder_path = os.path.join(outputs_dir, folder)
            if os.path.isdir(folder_path):
                folder_time = datetime.fromtimestamp(os.path.getctime(folder_path))
                if folder_time < cutoff_date:
                    logger.info(f"Удаляем старую папку: {folder_path}")
                    shutil.rmtree(folder_path)
    
    logger.info("Очистка старых файлов завершена")

@shared_task
def check_project_status(project_id: str):
    """Проверяет статус проекта и отправляет уведомление"""
    project = get_project(project_id)
    
    if not project:
        logger.error(f"Проект {project_id} не найден")
        return
    
    if project.status == "processing":
        # Проверяем, не завис ли проект
        if project.started_at:
            processing_time = (datetime.now() - project.started_at).total_seconds() / 60
            
            if processing_time > 120:  # Более 2 часов
                logger.warning(f"Проект {project_id} обрабатывается более 2 часов")
                
                # Отправляем предупреждение
                if project.telegram_chat_id:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(
                        notify_progress(
                            project.telegram_chat_id,
                            project_id,
                            "⚠️ Обработка занимает больше времени чем обычно.\n"
                            "Проверяем статус..."
                        )
                    )
    
    return {
        "project_id": project_id,
        "status": project.status,
        "processing_time": (datetime.now() - project.started_at).total_seconds() / 60 if project.started_at else 0
    }