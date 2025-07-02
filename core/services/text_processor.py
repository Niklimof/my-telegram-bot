# Путь: /youtube_automation_bot/core/services/text_processor.py
# Описание: Сервис обработки текста через Claude AI с поддержкой больших текстов

import anthropic
from typing import List, Dict, Any, Optional
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TextProcessor:
    """Обработка текста через Claude AI"""
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_tokens_per_request = 3000
        self.output_target = 20000  # Целевое количество слов
        
    async def process_to_20k_words(self, 
                                  original_text: str, 
                                  prompt: str,
                                  model: str = "claude-3-sonnet-20240229") -> str:
        """
        Обрабатывает текст до ~20k слов
        
        Args:
            original_text: Исходный текст транскрипции
            prompt: Промпт для обработки
            model: Модель Claude
            
        Returns:
            Обработанный текст ~20k слов
        """
        logger.info(f"Начинаем обработку текста. Исходный размер: {len(original_text.split())} слов")
        
        # Разбиваем текст на части
        chunks = self._split_text_smart(original_text)
        logger.info(f"Разбили текст на {len(chunks)} частей")
        
        # Обрабатываем каждую часть
        processed_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Обрабатываем часть {i+1}/{len(chunks)}")
            
            # Адаптируем промпт для достижения нужной длины
            chunk_prompt = self._adapt_prompt_for_length(
                prompt, 
                current_length=sum(len(p.split()) for p in processed_chunks),
                target_length=self.output_target,
                chunk_index=i,
                total_chunks=len(chunks)
            )
            
            processed = await self._process_chunk(chunk, chunk_prompt, model)
            processed_chunks.append(processed)
            
            # Небольшая пауза между запросами
            if i < len(chunks) - 1:
                await asyncio.sleep(2)
        
        # Объединяем результаты
        final_text = self._merge_chunks_intelligently(processed_chunks)
        
        word_count = len(final_text.split())
        logger.info(f"Обработка завершена. Итоговый размер: {word_count} слов")
        
        return final_text
    
    def _split_text_smart(self, text: str) -> List[str]:
        """Умное разбиение текста с учетом контекста"""
        # Примерный расчет: каждые 1000 слов исходного текста → 3000-4000 слов обработанного
        words = text.split()
        chunk_size = 800  # Слов на чанк
        
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            
            # Ищем конец предложения для чистого разреза
            chunk_text = ' '.join(chunk_words)
            if i + chunk_size < len(words):
                # Дополняем до конца предложения
                j = i + chunk_size
                while j < len(words) and not words[j-1].endswith('.'):
                    chunk_text += ' ' + words[j]
                    j += 1
            
            chunks.append(chunk_text)
        
        return chunks
    
    def _adapt_prompt_for_length(self, 
                                base_prompt: str, 
                                current_length: int,
                                target_length: int,
                                chunk_index: int,
                                total_chunks: int) -> str:
        """Адаптирует промпт для достижения целевой длины"""
        
        remaining_words = target_length - current_length
        words_per_chunk = remaining_words // (total_chunks - chunk_index)
        
        length_instruction = f"""
ВАЖНО: Этот фрагмент должен быть расширен примерно до {words_per_chunk} слов.
Добавь детали, примеры, объяснения и развей идеи для достижения нужного объема.
Сохраняй связность с предыдущими частями.
"""
        
        return f"{base_prompt}\n\n{length_instruction}"
    
    async def _process_chunk(self, chunk: str, prompt: str, model: str) -> str:
        """Обрабатывает один фрагмент текста"""
        
        message = f"{prompt}\n\nИсходный текст:\n{chunk}\n\nОбработанный текст:"
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.7,
                messages=[{"role": "user", "content": message}]
            )
        )
        
        return response.content[0].text
    
    def _merge_chunks_intelligently(self, chunks: List[str]) -> str:
        """Интеллектуальное объединение фрагментов"""
        
        if not chunks:
            return ""
        
        merged = chunks[0]
        
        for i in range(1, len(chunks)):
            # Удаляем возможные повторения в начале
            chunk = chunks[i]
            
            # Ищем логическую связку
            if chunk.startswith(('Кроме того,', 'Также', 'Далее', 'Продолжая')):
                merged += f"\n\n{chunk}"
            else:
                # Добавляем связующую фразу
                merged += f"\n\n{chunk}"
        
        return merged