# Путь: /youtube_automation_bot/core/services/speech_generator.py
# Описание: Оптимизированный генератор озвучки для больших текстов через Yandex SpeechKit

import aiohttp
import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SpeechGenerator:
    """Генератор озвучки через Yandex SpeechKit"""
    
    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        self.synthesis_url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
        self.max_chunk_size = 5000  # Максимум символов на запрос
        self.parallel_limit = 5  # Параллельных запросов
        
    async def generate_for_20k_words(self,
                                    text: str,
                                    output_dir: str,
                                    voice: str = "alena",
                                    emotion: str = "neutral",
                                    speed: float = 1.0) -> Dict[str, Any]:
        """
        Генерирует озвучку для текста ~20k слов
        
        Returns:
            Dict с информацией о сгенерированных файлах
        """
        start_time = datetime.now()
        
        # Создаем директорию
        os.makedirs(output_dir, exist_ok=True)
        
        # Разбиваем текст
        chunks = self._split_text_for_speech(text)
        logger.info(f"Разбили текст на {len(chunks)} частей для озвучки")
        
        # Генерируем озвучку
        audio_files = []
        total_duration = 0
        
        # Обрабатываем батчами
        for batch_start in range(0, len(chunks), self.parallel_limit):
            batch_end = min(batch_start + self.parallel_limit, len(chunks))
            batch = chunks[batch_start:batch_end]
            
            logger.info(f"Обрабатываем батч {batch_start//self.parallel_limit + 1}/{(len(chunks)-1)//self.parallel_limit + 1}")
            
            # Параллельная генерация батча
            tasks = []
            for i, chunk in enumerate(batch):
                chunk_index = batch_start + i
                output_path = os.path.join(output_dir, f"speech_{chunk_index:04d}.mp3")
                
                task = self._synthesize_chunk(
                    chunk, output_path, voice, emotion, speed
                )
                tasks.append(task)
            
            # Ждем завершения батча
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка генерации части {batch_start + i}: {result}")
                    # Повторная попытка
                    chunk_index = batch_start + i
                    output_path = os.path.join(output_dir, f"speech_{chunk_index:04d}.mp3")
                    try:
                        result = await self._synthesize_chunk(
                            chunks[chunk_index], output_path, voice, emotion, speed
                        )
                    except Exception as e:
                        logger.error(f"Повторная ошибка: {e}")
                        continue
                
                if result:
                    audio_files.append(result['path'])
                    total_duration += result.get('duration', 0)
            
            # Пауза между батчами
            if batch_end < len(chunks):
                await asyncio.sleep(3)
        
        end_time = datetime.now()
        generation_time = (end_time - start_time).total_seconds()
        
        # Создаем файл с порядком частей
        order_file = os.path.join(output_dir, "chunks_order.txt")
        with open(order_file, 'w', encoding='utf-8') as f:
            for i, path in enumerate(audio_files):
                f.write(f"{i:04d}|{path}\n")
        
        result = {
            "audio_files": audio_files,
            "chunks_count": len(audio_files),
            "total_duration": total_duration,
            "generation_time": generation_time,
            "output_dir": output_dir,
            "order_file": order_file,
            "voice": voice,
            "text_length": len(text),
            "words_count": len(text.split())
        }
        
        logger.info(f"Озвучка завершена: {len(audio_files)} файлов, "
                   f"~{total_duration/60:.1f} минут аудио, "
                   f"время генерации: {generation_time/60:.1f} минут")
        
        return result
    
    def _split_text_for_speech(self, text: str) -> List[str]:
        """Разбивает текст на части оптимального размера"""
        
        # Разбиваем по параграфам
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            # Если параграф сам по себе слишком большой
            if len(para) > self.max_chunk_size:
                # Сохраняем текущий чанк
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # Разбиваем большой параграф по предложениям
                sentences = para.split('. ')
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 2 < self.max_chunk_size:
                        current_chunk += sentence + ". "
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + ". "
            
            # Обычный параграф
            elif len(current_chunk) + len(para) + 4 < self.max_chunk_size:
                current_chunk += para + "\n\n"
            else:
                # Сохраняем текущий чанк и начинаем новый
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        # Последний чанк
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def _synthesize_chunk(self,
                               text: str,
                               output_path: str,
                               voice: str,
                               emotion: str,
                               speed: float) -> Dict[str, Any]:
        """Синтезирует один фрагмент"""
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}"
        }
        
        data = {
            "text": text,
            "lang": "ru-RU",
            "voice": voice,
            "emotion": emotion,
            "speed": str(speed),
            "format": "mp3",
            "folderId": self.folder_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.synthesis_url,
                headers=headers,
                data=data
            ) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    
                    # Сохраняем файл
                    with open(output_path, 'wb') as f:
                        f.write(audio_data)
                    
                    # Оценка длительности (примерная)
                    # ~150 слов в минуту для нормальной скорости
                    words = len(text.split())
                    duration = (words / 150) * 60 / speed  # в секундах
                    
                    return {
                        "path": output_path,
                        "duration": duration,
                        "size": len(audio_data),
                        "text_length": len(text)
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"SpeechKit error {response.status}: {error_text}")