# core/services/dual_claude_processor.py
# Обработка текста через два диалога Claude для создания качественных рассказов

import anthropic
from typing import Dict, Any, Optional
import asyncio
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DualClaudeProcessor:
    """
    Процессор использующий два диалога Claude:
    1. Первый создает план рассказа
    2. Второй пишет рассказ по плану
    """
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.target_words = 13500  # Для 90 минут видео
        
    async def process_with_dual_claude(self,
                                     transcription: str,
                                     plan_prompt_template: str,
                                     model: str = "claude-3-sonnet-20240229") -> Dict[str, Any]:
        """
        Обрабатывает текст через два диалога Claude
        
        Returns:
            Dict с планом и финальным рассказом
        """
        start_time = datetime.now()
        
        # ШАГ 1: Создание плана рассказа
        logger.info("Запускаем первый Claude для создания плана...")
        story_plan = await self._create_story_plan(
            transcription, 
            plan_prompt_template,
            model
        )
        
        # ШАГ 2: Написание рассказа по плану
        logger.info("Запускаем второй Claude для написания рассказа...")
        final_story = await self._write_story_from_plan(
            story_plan,
            model
        )
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return {
            "plan": story_plan,
            "story": final_story,
            "word_count": len(final_story.split()),
            "processing_time": processing_time
        }
    
    async def _create_story_plan(self, 
                                transcription: str,
                                prompt_template: str,
                                model: str) -> str:
        """Первый Claude: создает детальный план рассказа"""
        
        # Подставляем переменные в шаблон
        prompt = prompt_template.format(
            text=transcription,
            target_words=self.target_words
        )
        
        # Добавляем финальную инструкцию
        prompt += """

ФИНАЛЬНЫЙ ФОРМАТ ПЛАНА:
Создай структурированный план в следующем формате:
- Название рассказа
- Жанр и поджанр
- Основная идея (1-2 предложения)
- Главные персонажи с описанием
- Структура по актам с ключевыми сценами
- Важные детали и символы
- Эмоциональная кривая
- Финальное послание

План должен быть детальным и готовым для написания рассказа."""
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.7,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
        )
        
        plan = response.content[0].text
        logger.info(f"План создан, длина: {len(plan)} символов")
        
        return plan
    
    async def _write_story_from_plan(self,
                                    story_plan: str,
                                    model: str) -> str:
        """Второй Claude: пишет рассказ по готовому плану"""
        
        # Промпт для второго Claude (из Google Doc)
        story_prompt = f"""Ты - мастер художественного слова, создающий захватывающие аудио-рассказы.

Твоя задача: написать полноценный рассказ строго по готовому плану.

ПЛАН РАССКАЗА:
{story_plan}

ТРЕБОВАНИЯ К РАССКАЗУ:
1. Объем: {self.target_words} слов (это примерно 90 минут аудио)
2. Стиль: яркий, эмоциональный, захватывающий с первых строк
3. Структура: следуй плану, но развивай каждую сцену детально
4. Диалоги: живые, естественные, продвигающие сюжет
5. Описания: яркие, но не перегруженные, создающие атмосферу
6. Темп: динамичный, без затянутых моментов

ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ ДЛЯ АУДИО:
- Используй многоточия для естественных пауз
- Разделяй текст на абзацы для удобства озвучки
- Избегай сложных конструкций, которые трудно воспринимать на слух
- Каждая сцена должна быть законченной

ВАЖНО:
- Не отклоняйся от плана
- Развивай каждую сцену до полноценного эпизода
- Создавай эмоциональную вовлеченность
- Пиши так, чтобы слушатель не мог оторваться

Начни рассказ сразу, без предисловий."""
        
        # Разбиваем на части если план большой
        chunks = await self._process_story_in_chunks(story_prompt, model)
        
        # Объединяем части
        final_story = self._merge_story_chunks(chunks)
        
        word_count = len(final_story.split())
        logger.info(f"Рассказ написан: {word_count} слов")
        
        # Если нужно добавить объем
        if word_count < self.target_words * 0.9:
            final_story = await self._expand_story(final_story, story_plan, model)
        
        return final_story
    
    async def _process_story_in_chunks(self, prompt: str, model: str) -> list:
        """Обрабатывает длинный рассказ по частям"""
        
        chunks = []
        sections = [
            "начало (первые 25%)",
            "развитие действия (следующие 25%)",
            "кульминация (следующие 25%)",
            "развязка и финал (последние 25%)"
        ]
        
        for i, section in enumerate(sections):
            section_prompt = f"{prompt}\n\nСейчас напиши {section} рассказа. Это часть {i+1} из {len(sections)}."
            
            if i > 0:
                section_prompt += f"\n\nПредыдущая часть закончилась на:\n{chunks[-1][-500:]}\n\nПродолжай с этого момента."
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=model,
                    max_tokens=4000,
                    temperature=0.8,
                    messages=[{
                        "role": "user",
                        "content": section_prompt
                    }]
                )
            )
            
            chunks.append(response.content[0].text)
            
            # Пауза между запросами
            if i < len(sections) - 1:
                await asyncio.sleep(2)
        
        return chunks
    
    def _merge_story_chunks(self, chunks: list) -> str:
        """Объединяет части рассказа"""
        
        if not chunks:
            return ""
        
        # Первая часть целиком
        merged = chunks[0]
        
        # Остальные части с удалением возможных повторов
        for i in range(1, len(chunks)):
            chunk = chunks[i]
            
            # Ищем плавный переход
            # Удаляем первый абзац если он повторяет конец предыдущего
            paragraphs = chunk.split('\n\n')
            if paragraphs and merged.rstrip().endswith(paragraphs[0].strip()[:50]):
                chunk = '\n\n'.join(paragraphs[1:])
            
            merged += '\n\n' + chunk
        
        return merged.strip()
    
    async def _expand_story(self, story: str, plan: str, model: str) -> str:
        """Расширяет рассказ если он короче целевого объема"""
        
        current_words = len(story.split())
        needed_words = self.target_words - current_words
        
        logger.info(f"Расширяем рассказ: нужно добавить ~{needed_words} слов")
        
        expand_prompt = f"""Рассказ получился короче необходимого. Нужно расширить его на {needed_words} слов.

ПЛАН РАССКАЗА:
{plan}

ТЕКУЩИЙ РАССКАЗ:
{story}

ЗАДАЧА:
1. Добавь детальные описания ключевых сцен
2. Расширь диалоги персонажей
3. Добавь внутренние монологи и размышления
4. Углуби эмоциональные моменты
5. Добавь атмосферные детали

Верни ТОЛЬКО добавленные фрагменты, которые нужно вставить в соответствующие места рассказа."""
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.8,
                messages=[{
                    "role": "user",
                    "content": expand_prompt
                }]
            )
        )
        
        additions = response.content[0].text
        
        # Интегрируем дополнения в рассказ
        # В реальности нужна более сложная логика вставки
        expanded_story = story + "\n\n" + additions
        
        return expanded_story