# Путь: /youtube_automation_bot/core/services/robust_text_processor.py
# Описание: Улучшенный процессор текста с обработкой ошибок и управлением контекстом

import anthropic
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import logging
import hashlib
import pickle
import os
from datetime import datetime
import backoff

logger = logging.getLogger(__name__)

class RobustTextProcessor:
    """Надежный процессор текста с управлением контекстом и кешированием"""
    
    def __init__(self, api_key: str, cache_dir: str = "cache/claude"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # Лимиты для безопасной работы
        self.max_input_tokens = 20000    # Безопасный лимит входа
        self.max_output_tokens = 4000    # Лимит выхода
        self.overlap_tokens = 2000       # Перекрытие между чанками
        self.max_retries = 3
        
    def estimate_tokens(self, text: str) -> int:
        """Оценка количества токенов"""
        # Для русского: ~4 символа на токен
        # Для английского: ~4 символа на токен
        return len(text) // 4
    
    async def process_to_20k_words(self, 
                                  original_text: str, 
                                  prompt: str,
                                  model: str = "claude-3-sonnet-20240229",
                                  use_cache: bool = True) -> str:
        """
        Обрабатывает текст до ~20k слов с умным управлением контекстом
        """
        # Проверяем кеш
        if use_cache:
            cache_key = self._get_cache_key(original_text, prompt, model)
            cached_result = self._load_from_cache(cache_key)
            if cached_result:
                logger.info("Используем кешированный результат")
                return cached_result
        
        try:
            # Оцениваем размер входного текста
            input_tokens = self.estimate_tokens(original_text)
            logger.info(f"Estimated input tokens: {input_tokens}")
            
            if input_tokens > self.max_input_tokens:
                # Обработка с разбиением
                result = await self._process_with_sliding_window(
                    original_text, prompt, model
                )
            else:
                # Простая обработка
                result = await self._process_single_with_retry(
                    original_text, prompt, model
                )
            
            # Проверяем результат
            word_count = len(result.split())
            logger.info(f"Generated {word_count} words")
            
            # Если нужно больше слов, дорабатываем
            if word_count < 18000:
                result = await self._expand_text(result, prompt, model, 20000 - word_count)
            
            # Сохраняем в кеш
            if use_cache:
                self._save_to_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in text processing: {str(e)}")
            raise
    
    async def _process_with_sliding_window(self, 
                                         text: str, 
                                         prompt: str,
                                         model: str) -> str:
        """Обработка длинного текста с перекрывающимися окнами"""
        
        # Разбиваем текст на чанки с перекрытием
        chunks = self._create_overlapping_chunks(text)
        logger.info(f"Split text into {len(chunks)} overlapping chunks")
        
        processed_parts = []
        context_summary = ""
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            
            # Адаптируем промпт с учетом контекста
            chunk_prompt = self._build_contextual_prompt(
                base_prompt=prompt,
                chunk_index=i,
                total_chunks=len(chunks),
                previous_summary=context_summary,
                target_words_per_chunk=20000 // len(chunks)
            )
            
            # Обрабатываем чанк
            processed = await self._process_single_with_retry(
                chunk, chunk_prompt, model
            )
            
            processed_parts.append(processed)
            
            # Обновляем контекст для следующего чанка
            context_summary = self._extract_summary(processed)
            
            # Пауза между запросами
            if i < len(chunks) - 1:
                await asyncio.sleep(2)
        
        # Объединяем результаты
        return self._merge_chunks_intelligently(processed_parts)
    
    def _create_overlapping_chunks(self, text: str) -> List[Tuple[str, int, int]]:
        """Создает чанки с перекрытием"""
        words = text.split()
        chunk_size = self.max_input_tokens * 4 // 5  # ~80% от лимита в символах
        overlap_size = self.overlap_tokens * 4
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Находим конец чанка
            end = start + chunk_size
            
            # Корректируем по границе предложения
            if end < len(text):
                # Ищем конец предложения
                while end < len(text) and text[end] not in '.!?':
                    end += 1
                end += 1  # Включаем точку
            
            chunk = text[start:end]
            chunks.append((chunk, start, end))
            
            # Следующий чанк с перекрытием
            start = end - overlap_size
            
            # Корректируем начало по границе предложения
            if start > 0 and start < len(text):
                while start > 0 and text[start-1] not in '.!?':
                    start -= 1
        
        return chunks
    
    def _build_contextual_prompt(self, 
                                base_prompt: str,
                                chunk_index: int,
                                total_chunks: int,
                                previous_summary: str,
                                target_words_per_chunk: int) -> str:
        """Создает промпт с учетом контекста"""
        
        context_part = ""
        if previous_summary:
            context_part = f"\nКонтекст из предыдущей части:\n{previous_summary}\n"
        
        position_part = f"\nЭто часть {chunk_index + 1} из {total_chunks}."
        
        length_instruction = f"""
ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Этот фрагмент должен содержать примерно {target_words_per_chunk} слов
2. Детально развей все идеи, добавь примеры и объяснения
3. Сохраняй связность с предыдущими частями
4. {f'Продолжай развитие темы из предыдущей части' if chunk_index > 0 else 'Начни с введения в тему'}
"""
        
        return f"{base_prompt}{context_part}{position_part}\n{length_instruction}"
    
    @backoff.on_exception(
        backoff.expo,
        (anthropic.APIError, asyncio.TimeoutError),
        max_tries=3,
        max_time=300
    )
    async def _process_single_with_retry(self, 
                                       text: str, 
                                       prompt: str,
                                       model: str) -> str:
        """Обработка одного фрагмента с retry логикой"""
        
        try:
            message = f"{prompt}\n\nТекст для обработки:\n{text}\n\nОбработанный текст:"
            
            # Используем asyncio для таймаута
            loop = asyncio.get_event_loop()
            
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.client.messages.create(
                        model=model,
                        max_tokens=self.max_output_tokens,
                        temperature=0.7,
                        messages=[{"role": "user", "content": message}]
                    )
                ),
                timeout=120  # 2 минуты таймаут
            )
            
            return response.content[0].text
            
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {str(e)}")
            if "rate_limit" in str(e).lower():
                # Более длительная пауза при rate limit
                await asyncio.sleep(60)
            raise
        except asyncio.TimeoutError:
            logger.error("Request timed out")
            raise
    
    def _merge_chunks_intelligently(self, chunks: List[str]) -> str:
        """Интеллектуальное объединение чанков с удалением дублирований"""
        
        if not chunks:
            return ""
        
        merged = chunks[0]
        
        for i in range(1, len(chunks)):
            current_chunk = chunks[i]
            
            # Находим перекрытие
            overlap = self._find_overlap(merged, current_chunk)
            
            if overlap and len(overlap) > 100:  # Значимое перекрытие
                # Удаляем перекрытие из начала текущего чанка
                overlap_index = current_chunk.find(overlap)
                if overlap_index != -1:
                    current_chunk = current_chunk[overlap_index + len(overlap):]
            
            # Добавляем связку если нужно
            if not merged.rstrip().endswith(('.', '!', '?')):
                merged += "."
            
            merged += "\n\n" + current_chunk.lstrip()
        
        return merged
    
    def _find_overlap(self, text1: str, text2: str, min_length: int = 50) -> Optional[str]:
        """Находит перекрывающийся текст между концом text1 и началом text2"""
        
        # Ищем совпадения длиной от min_length
        for length in range(min(len(text1), len(text2), 500), min_length, -1):
            if text1[-length:] == text2[:length]:
                return text1[-length:]
        
        return None
    
    def _extract_summary(self, text: str, max_length: int = 500) -> str:
        """Извлекает краткое резюме из текста для контекста"""
        
        sentences = text.split('.')
        summary = []
        current_length = 0
        
        # Берем первые и последние предложения
        important_sentences = sentences[:2] + sentences[-2:] if len(sentences) > 4 else sentences
        
        for sentence in important_sentences:
            sentence = sentence.strip()
            if sentence and current_length + len(sentence) < max_length:
                summary.append(sentence)
                current_length += len(sentence)
        
        return '. '.join(summary) + '.'
    
    async def _expand_text(self, 
                          text: str, 
                          original_prompt: str,
                          model: str,
                          target_additional_words: int) -> str:
        """Расширяет текст до нужного количества слов"""
        
        expansion_prompt = f"""
{original_prompt}

Текст нужно расширить, добавив еще примерно {target_additional_words} слов.
Добавь больше деталей, примеров, объяснений и развития идей.
Сохрани стиль и тон оригинального текста.

Исходный текст для расширения:
{text[-3000:]}  # Последняя часть для контекста

Продолжение:
"""
        
        expansion = await self._process_single_with_retry(
            text[-3000:], expansion_prompt, model
        )
        
        return text + "\n\n" + expansion
    
    def _get_cache_key(self, text: str, prompt: str, model: str) -> str:
        """Генерирует ключ кеша"""
        content = f"{text[:1000]}:{prompt}:{model}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _load_from_cache(self, cache_key: str) -> Optional[str]:
        """Загружает из кеша"""
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return None
    
    def _save_to_cache(self, cache_key: str, data: str):
        """Сохраняет в кеш"""
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.pkl")
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")