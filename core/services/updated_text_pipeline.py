# core/pipeline/updated_text_pipeline.py
# Обновленный pipeline с двойной обработкой Claude

import asyncio
from typing import Dict, Any, Optional
import logging
from datetime import datetime

from core.services.youtube_downloader import YouTubeDownloader
from core.services.transcriber import Transcriber
from core.services.dual_claude_processor import DualClaudeProcessor
from core.services.speech_generator import SpeechGenerator
from core.services.storage_manager import YandexDiskManager

logger = logging.getLogger(__name__)

class UpdatedTextPipeline:
    """Pipeline для создания рассказов с двойной обработкой Claude"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Инициализация сервисов
        self.youtube = YouTubeDownloader()
        self.transcriber = Transcriber(model_size=config.get("whisper_model", "large"))
        self.text_processor = DualClaudeProcessor(api_key=config["claude_api_key"])
        self.speech_generator = SpeechGenerator(
            api_key=config["speechkit_api_key"],
            folder_id=config["speechkit_folder_id"]
        )
        self.storage = YandexDiskManager(token=config["yandex_disk_token"])
        
    async def process(self, 
                     project_id: str,
                     youtube_url: str,
                     plan: Dict[str, Any],
                     callbacks: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Выполняет полную обработку видео
        """
        start_time = datetime.now()
        results = {
            "project_id": project_id,
            "status": "processing",
            "steps": {}
        }
        
        try:
            # 1. Загрузка видео
            await self._notify(callbacks, "download_start", "🎬 Начинаю загрузку видео...")
            
            video_info = await self.youtube.download(youtube_url, f"downloads/{project_id}")
            results["steps"]["download"] = {
                "status": "completed",
                "video_path": video_info["path"],
                "duration": video_info["duration"],
                "title": video_info["title"]
            }
            
            await self._notify(callbacks, "download_complete", 
                             f"✅ Видео загружено: {video_info['title']}")
            
            # 2. Извлечение аудио и транскрибация
            await self._notify(callbacks, "transcribe_start", "🎤 Начинаю транскрибацию...")
            
            audio_path = await self.youtube.extract_audio(video_info["path"])
            transcription = await self.transcriber.transcribe(audio_path)
            
            results["steps"]["transcription"] = {
                "status": "completed",
                "text": transcription["text"],
                "word_count": len(transcription["text"].split()),
                "language": transcription.get("language", "ru")
            }
            
            await self._notify(callbacks, "transcribe_complete", 
                             f"✅ Транскрибация завершена: {len(transcription['text'].split())} слов")
            
            # 3. Двойная обработка через Claude
            await self._notify(callbacks, "process_start", 
                             "🤖 Запускаю двойную обработку Claude AI...")
            
            # Находим шаги для двух Claude
            plan_step = next(
                (step for step in plan["text_steps"] if step["type"] == "create_story_plan"),
                None
            )
            
            if not plan_step:
                # Fallback на старый формат
                plan_step = next(
                    (step for step in plan["text_steps"] if step["type"] == "process_with_claude"),
                    None
                )
            
            if not plan_step:
                raise ValueError("Шаг обработки Claude не найден в плане")
            
            # Запускаем двойную обработку
            await self._notify(callbacks, "claude_plan_start", 
                             "📝 Claude #1: Создаю план рассказа...")
            
            processing_result = await self.text_processor.process_with_dual_claude(
                transcription["text"],
                plan_step["params"]["prompt"],
                plan_step["params"].get("model", "claude-3-sonnet-20240229")
            )
            
            await self._notify(callbacks, "claude_story_start", 
                             "✍️ Claude #2: Пишу рассказ по плану...")
            
            results["steps"]["text_processing"] = {
                "status": "completed",
                "plan": processing_result["plan"],
                "story": processing_result["story"],
                "word_count": processing_result["word_count"],
                "processing_time": processing_result["processing_time"]
            }
            
            await self._notify(callbacks, "process_complete", 
                             f"✅ Рассказ создан: {processing_result['word_count']} слов")
            
            # 4. Генерация озвучки
            await self._notify(callbacks, "speech_start", 
                             "🔊 Начинаю генерацию озвучки через SpeechKit...")
            
            # Получаем параметры озвучки
            speech_step = next(
                (step for step in plan["text_steps"] if step["type"] == "generate_speech"),
                None
            )
            
            if not speech_step:
                raise ValueError("Шаг генерации речи не найден в плане")
            
            # Генерируем озвучку для рассказа
            speech_result = await self.speech_generator.generate_for_20k_words(
                processing_result["story"],
                f"outputs/{project_id}/audio",
                voice=speech_step["params"].get("voice", "alena"),
                emotion=speech_step["params"].get("emotion", "neutral"),
                speed=speech_step["params"].get("speed", 1.0)
            )
            
            results["steps"]["speech_generation"] = {
                "status": "completed",
                "audio_files": speech_result["audio_files"],
                "chunks_count": speech_result["chunks_count"],
                "total_duration": speech_result["total_duration"],
                "voice": speech_result["voice"]
            }
            
            await self._notify(callbacks, "speech_complete", 
                             f"✅ Озвучка создана: {speech_result['chunks_count']} файлов, "
                             f"~{speech_result['total_duration']/60:.1f} минут")
            
            # 5. Сохранение результатов на Яндекс.Диск
            await self._notify(callbacks, "upload_start", 
                             "☁️ Загружаю результаты на Яндекс.Диск...")
            
            # Сохраняем план
            plan_file = f"outputs/{project_id}/story_plan.txt"
            with open(plan_file, 'w', encoding='utf-8') as f:
                f.write("=== ПЛАН РАССКАЗА ===\n\n")
                f.write(processing_result["plan"])
            
            # Сохраняем рассказ
            story_file = f"outputs/{project_id}/final_story.txt"
            with open(story_file, 'w', encoding='utf-8') as f:
                f.write(processing_result["story"])
            
            # Создаем метаданные
            metadata_file = f"outputs/{project_id}/metadata.json"
            import json
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "project_id": project_id,
                    "youtube_url": youtube_url,
                    "original_title": video_info["title"],
                    "original_duration": video_info["duration"],
                    "transcription_words": len(transcription["text"].split()),
                    "story_words": processing_result["word_count"],
                    "audio_duration": speech_result["total_duration"],
                    "processing_time": (datetime.now() - start_time).total_seconds(),
                    "plan_name": plan.get("name", "Unknown"),
                    "voice": speech_result["voice"]
                }, f, ensure_ascii=False, indent=2)
            
            # Структура папок на Я.Диске
            folder_structure = {
                "text": [plan_file, story_file],
                "audio": speech_result["audio_files"],
                "meta": [metadata_file, speech_result["order_file"]]
            }
            
            upload_result = await self.storage.upload_project(
                project_id,
                folder_structure,
                metadata={
                    "project_id": project_id,
                    "youtube_url": youtube_url,
                    "original_title": video_info["title"],
                    "word_count": processing_result["word_count"],
                    "audio_duration": speech_result["total_duration"],
                    "processing_time": (datetime.now() - start_time).total_seconds()
                }
            )
            
            results["steps"]["upload"] = {
                "status": "completed",
                "folder_url": upload_result["folder_url"],
                "files_uploaded": upload_result["files_count"]
            }
            
            await self._notify(callbacks, "upload_complete", 
                             f"✅ Файлы загружены: {upload_result['folder_url']}")
            
            # Финальный результат
            results["status"] = "completed"
            results["processing_time"] = (datetime.now() - start_time).total_seconds()
            results["yandex_folder_url"] = upload_result["folder_url"]
            
            await self._notify(callbacks, "pipeline_complete", 
                             f"🎉 Обработка завершена за {results['processing_time']/60:.1f} минут!\n"
                             f"📁 Результаты: {upload_result['folder_url']}")
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка в pipeline: {str(e)}")
            results["status"] = "failed"
            results["error"] = str(e)
            
            await self._notify(callbacks, "pipeline_error", f"❌ Ошибка: {str(e)}")
            
            raise
    
    async def _notify(self, callbacks: Optional[Dict[str, Any]], event: str, message: str):
        """Отправляет уведомление через коллбек"""
        if callbacks and event in callbacks:
            try:
                await callbacks[event](message)
            except Exception as e:
                logger.error(f"Ошибка в коллбеке {event}: {e}")