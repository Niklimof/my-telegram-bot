# workers/tasks/text_tasks.py
# Celery задачи с двойной обработкой Claude

from celery import shared_task
from database.crud import update_project, add_log, get_project, get_plan
from config.settings import settings
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_text_pipeline(self, project_id: str):
    """Запускает pipeline обработки текста с двойной обработкой Claude"""
    
    try:
        # Импортируем здесь чтобы избежать циклических импортов
        from core.pipeline.updated_text_pipeline import UpdatedTextPipeline
        
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
        
        # Создаем pipeline
        config = {
            "whisper_model": project.settings.whisper_model if project.settings else "large",
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
                try:
                    # Динамический импорт для избежания циклических зависимостей
                    from interfaces.telegram_bot.bot import bot
                    await bot.send_message(
                        project.telegram_chat_id,
                        f"📊 Проект `{project_id[:8]}...`\n{message}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления: {e}")
        
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
        
        # Преобразуем план в словарь
        plan_dict = {
            "name": plan.name,
            "description": plan.description,
            "text_steps": plan.text_steps,
            "video_steps": plan.video_steps,
            "default_prompt": plan.default_prompt,
            "default_voice": plan.default_voice,
            "modules_enabled": plan.modules_enabled,
            "metadata": plan.metadata if hasattr(plan, 'metadata') else {}
        }
        
        results = loop.run_until_complete(
            pipeline.process(
                project_id=project_id,
                youtube_url=project.youtube_url,
                plan=plan_dict,
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
            try:
                from interfaces.telegram_bot.bot import bot
                loop.run_until_complete(
                    bot.send_message(
                        project.telegram_chat_id,
                        f"🎉 Ваш рассказ готов!\n"
                        f"📁 Скачать: {results['yandex_folder_url']}\n"
                        f"⏱ Длительность: ~{results['steps']['speech_generation']['total_duration']/60:.1f} минут\n"
                        f"📝 Слов: {results['steps']['text_processing']['word_count']}",
                        parse_mode="Markdown"
                    )
                )
            except Exception as e:
                logger.error(f"Ошибка отправки финального уведомления: {e}")
        
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
                from interfaces.telegram_bot.bot import bot
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    bot.send_message(
                        project.telegram_chat_id,
                        f"❌ Произошла ошибка при обработке проекта `{project_id[:8]}...`\n"
                        f"Попробуем еще раз через 5 минут.",
                        parse_mode="Markdown"
                    )
                )
        except:
            pass
        
        # Повторная попытка
        raise self.retry(exc=e, countdown=300)  # Повтор через 5 минут