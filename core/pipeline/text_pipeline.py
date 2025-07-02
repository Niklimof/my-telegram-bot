# Путь: /youtube_automation_bot/core/pipeline/text_pipeline.py
# Описание: Pipeline для обработки текста (Фаза 1)

import asyncio
from typing import Dict, Any, Optional
import logging
from datetime import datetime

from core.services.youtube_downloader import YouTubeDownloader
from core.services.transcriber import Transcriber
from core.services.text_processor import TextProcessor
from core.services.speech_generator import SpeechGenerator
from core.services.storage_manager import YandexDiskManager

logger = logging.getLogger(__name__)

class TextPipeline:
    """Pipeline для фазы 1: текст и озвучка"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Инициализация сервисов
        self.youtube = YouTubeDownloader()
        self.transcriber = Transcriber(model_size=config.get("whisper_model", "medium"))
        self.text_processor = TextProcessor(api_key=config["claude_api_key"])
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
        Выполняет полную обработку видео по фазе 1
        
        Args:
            project_id: ID проекта
            youtube_url: URL YouTube видео
            plan: План обработки
            callbacks: Коллбеки для уведомлений о прогрессе
            
        Returns:
            Результаты обработки
        """
        start_time = datetime.now()
        results = {
            "project_id": project_id,
            "status": "processing",
            "steps": {}
        }
        
        try:
            # 1. Загрузка видео
            await self._notify(callbacks, "download_start", "Начинаю загрузку видео...")
            
            video_info = await self.youtube.download(youtube_url, f"downloads/{project_id}")
            results["steps"]["download"] = {
                "status": "completed",
                "video_path": video_info["path"],
                "duration": video_info["duration"],
                "title": video_info["title"]
            }
            
            await self._notify(callbacks, "download_complete", 
                             f"Видео загружено: {video_info['title']}")
            
            # 2. Извлечение аудио и транскрибация
            await self._notify(callbacks, "transcribe_start", "Начинаю транскрибацию...")
            
            audio_path = await self.youtube.extract_audio(video_info["path"])
            transcription = await self.transcriber.transcribe(audio_path)
            
            results["steps"]["transcription"] = {
                "status": "completed",
                "text": transcription["text"],
                "word_count": len(transcription["text"].split()),
                "language": transcription.get("language", "ru")
            }
            
            await self._notify(callbacks, "transcribe_complete", 
                             f"Транскрибация завершена: {len(transcription['text'].split())} слов")
            
            # 3. Обработка текста через Claude
            await self._notify(callbacks, "process_start", 
                             "Начинаю обработку текста через Claude AI...")
            
            # Получаем промпт из плана
            claude_step = next(
                (step for step in plan["text_steps"] if step["type"] == "process_with_claude"),
                None
            )
            
            if not claude_step:
                raise ValueError("Шаг обработки Claude не найден в плане")
            
            processed_text = await self.text_processor.process_to_20k_words(
                transcription["text"],
                claude_step["params"]["prompt"],
                claude_step["params"].get("model", "claude-3-sonnet-20240229")
            )
            
            results["steps"]["text_processing"] = {
                "status": "completed",
                "text": processed_text,
                "word_count": len(processed_text.split()),
                "prompt_used": claude_step["params"]["prompt"][:100] + "..."
            }
            
            await self._notify(callbacks, "process_complete", 
                             f"Текст обработан: {len(processed_text.split())} слов")
            
            # 4. Генерация озвучки
            await self._notify(callbacks, "speech_start", 
                             "Начинаю генерацию озвучки через SpeechKit...")
            
            # Получаем параметры озвучки из плана
            speech_step = next(
                (step for step in plan["text_steps"] if step["type"] == "generate_speech"),
                None
            )
            
            if not speech_step:
                raise ValueError("Шаг генерации речи не найден в плане")
            
            speech_result = await self.speech_generator.generate_for_20k_words(
                processed_text,
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
                             f"Озвучка создана: {speech_result['chunks_count']} файлов, "
                             f"~{speech_result['total_duration']/60:.1f} минут")
            
            # 5. Сохранение результатов на Яндекс.Диск
            await self._notify(callbacks, "upload_start", 
                             "Загружаю результаты на Яндекс.Диск...")
            
            # Сохраняем текст
            text_file = f"outputs/{project_id}/processed_text.txt"
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(processed_text)
            
            # Создаем структуру папок на Я.Диске
            folder_structure = {
                "text": [text_file],
                "audio": speech_result["audio_files"],
                "meta": [speech_result["order_file"]]
            }
            
            upload_result = await self.storage.upload_project(
                project_id,
                folder_structure,
                metadata={
                    "project_id": project_id,
                    "youtube_url": youtube_url,
                    "original_title": video_info["title"],
                    "word_count": len(processed_text.split()),
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
                             f"Файлы загружены на Яндекс.Диск: {upload_result['folder_url']}")
            
            # Финальный результат
            results["status"] = "completed"
            results["processing_time"] = (datetime.now() - start_time).total_seconds()
            results["yandex_folder_url"] = upload_result["folder_url"]
            
            await self._notify(callbacks, "pipeline_complete", 
                             f"Обработка завершена за {results['processing_time']/60:.1f} минут")
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка в pipeline: {str(e)}")
            results["status"] = "failed"
            results["error"] = str(e)
            
            await self._notify(callbacks, "pipeline_error", f"Ошибка: {str(e)}")
            
            raise
    
    async def _notify(self, callbacks: Optional[Dict[str, Any]], event: str, message: str):
        """Отправляет уведомление через коллбек"""
        if callbacks and event in callbacks:
            try:
                await callbacks[event](message)
            except Exception as e:
                logger.error(f"Ошибка в коллбеке {event}: {e}")