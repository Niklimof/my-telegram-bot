# interfaces/telegram_bot/notifications.py
import logging
import os

logger = logging.getLogger(__name__)

# Временно отключаем создание бота здесь
bot = None

async def notify_progress(chat_id: int, project_id: str, message: str):
    """Отправляет уведомление о прогрессе обработки"""
    # Временно просто логируем
    logger.info(f"[NOTIFICATION] {project_id}: {message}")
    print(f"[NOTIFICATION] {project_id}: {message}")