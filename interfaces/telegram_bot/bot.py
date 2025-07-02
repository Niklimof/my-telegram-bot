# interfaces/telegram_bot/bot.py
# Telegram бот для управления обработкой видео

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import uuid
import sys
import os

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from database.crud import create_project, get_plans, get_default_settings, get_project

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

# Состояния
class VideoStates(StatesGroup):
    waiting_for_url = State()
    selecting_plan = State()

# Хранилище активных проектов пользователей
user_projects = {}

# Команды
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Новое видео", callback_data="new_video")],
        [InlineKeyboardButton(text="📊 Мои проекты", callback_data="my_projects")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    await message.answer(
        "👋 Привет! Я помогу автоматизировать обработку YouTube видео.\n\n"
        "🎯 Что я умею:\n"
        "• Скачивать видео с YouTube\n"
        "• Транскрибировать речь в текст\n"
        "• Обрабатывать текст через Claude AI (~20k слов)\n"
        "• Создавать озвучку через Yandex SpeechKit\n"
        "• Сохранять результаты на Яндекс.Диск\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "new_video")
async def new_video_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📹 Отправьте ссылку на YouTube видео:\n\n"
        "Поддерживаются форматы:\n"
        "• https://youtube.com/watch?v=...\n"
        "• https://youtu.be/...\n"
        "• https://m.youtube.com/watch?v=..."
    )
    await state.set_state(VideoStates.waiting_for_url)
    await callback.answer()

@dp.message(VideoStates.waiting_for_url)
async def process_url(message: types.Message, state: FSMContext):
    url = message.text
    
    # Валидация URL
    if not any(domain in url for domain in ["youtube.com", "youtu.be", "m.youtube.com"]):
        await message.answer(
            "❌ Пожалуйста, отправьте корректную ссылку на YouTube видео\n"
            "Пример: https://youtube.com/watch?v=dQw4w9WgXcQ"
        )
        return
    
    # Сохраняем URL
    await state.update_data(youtube_url=url)
    
    # Получаем активные планы
    plans = get_plans(is_active=True)
    
    if not plans:
        await message.answer(
            "❌ Нет доступных планов обработки.\n"
            "Обратитесь к администратору для создания плана."
        )
        await state.clear()
        return
    
    # Создаем клавиатуру с планами
    keyboard_buttons = []
    for plan in plans:
        # Добавляем описание плана
        button_text = f"📋 {plan.name}"
        if plan.description:
            button_text += f"\n💡 {plan.description[:50]}..."
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"plan_{plan.id}"
            )
        ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(
        "📋 Выберите план обработки:\n\n"
        "Каждый план содержит настройки для обработки видео",
        reply_markup=keyboard
    )
    await state.set_state(VideoStates.selecting_plan)

@dp.callback_query(lambda c: c.data.startswith("plan_"))
async def select_plan_callback(callback: types.CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    
    # Создаем проект
    project_id = str(uuid.uuid4())
    settings_obj = get_default_settings()
    
    project = create_project({
        "id": project_id,
        "youtube_url": data["youtube_url"],
        "plan_id": plan_id,
        "settings_id": settings_obj.id if settings_obj else 1,
        "telegram_user_id": callback.from_user.id,
        "telegram_chat_id": callback.message.chat.id,
        "phase": 1,  # Фаза 1 - текст и озвучка
        "status": "created"
    })
    
    # Сохраняем проект для пользователя
    user_id = callback.from_user.id
    if user_id not in user_projects:
        user_projects[user_id] = []
    user_projects[user_id].append(project_id)
    
    await callback.message.edit_text(
        f"✅ Проект создан!\n"
        f"ID: `{project_id}`\n\n"
        f"🚀 Запускаю обработку...\n\n"
        f"⏱ Примерное время: 60-90 минут\n"
        f"📊 Вы получите уведомления о прогрессе",
        parse_mode="Markdown"
    )
    
    # Запускаем обработку через Celery
    try:
        # Импортируем здесь, чтобы избежать циклического импорта
        from workers.tasks.simple_tasks import process_video_simple
        process_video_simple.delay(project_id, data["youtube_url"])
        logger.info(f"Задача отправлена в Celery для проекта {project_id}")
    except ImportError:
        logger.error("Не удалось импортировать Celery задачу")
        await callback.message.answer(
            "⚠️ Сервис обработки временно недоступен. "
            "Попробуйте позже или обратитесь к администратору."
        )
    except Exception as e:
        logger.error(f"Ошибка при запуске задачи: {e}")
        await callback.message.answer(
            "❌ Произошла ошибка при запуске обработки. "
            "Попробуйте позже."
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "my_projects")
async def my_projects_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id not in user_projects or not user_projects[user_id]:
        await callback.message.answer(
            "📊 У вас пока нет проектов.\n"
            "Нажмите '📹 Новое видео' чтобы начать."
        )
        await callback.answer()
        return
    
    # Показываем последние 5 проектов
    recent_projects = user_projects[user_id][-5:]
    
    text = "📊 Ваши последние проекты:\n\n"
    
    for project_id in reversed(recent_projects):
        project = get_project(project_id)
        if project:
            status_emoji = {
                "created": "🆕",
                "processing": "⚙️",
                "completed": "✅",
                "failed": "❌"
            }.get(project.status, "❓")
            
            text += f"{status_emoji} `{project_id[:8]}...`\n"
            text += f"   Статус: {project.status}\n"
            
            if project.processed_word_count:
                text += f"   Слов: {project.processed_word_count}\n"
            
            if project.yandex_folder_url:
                text += f"   [Результаты]({project.yandex_folder_url})\n"
            
            text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_projects")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    help_text = """
❓ **Помощь по использованию бота**

**Как обработать видео:**
1. Нажмите "📹 Новое видео"
2. Отправьте ссылку на YouTube
3. Выберите план обработки
4. Дождитесь завершения (~60-90 минут)

**Что происходит при обработке:**
• Видео скачивается с YouTube
• Извлекается аудио дорожка
• Речь транскрибируется в текст
• Текст обрабатывается через Claude AI
• Создается новый текст ~20k слов
• Генерируется озвучка через SpeechKit
• Результаты сохраняются на Яндекс.Диск

**Требования:**
• Видео должно быть публичным
• Язык видео - русский
• Длительность - любая

**Результаты:**
• Обработанный текст (txt)
• Озвучка по частям (mp3)
• Метаданные проекта

При возникновении проблем обратитесь к администратору.
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.answer(
        help_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена")
    await cmd_start(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "refresh_projects")
async def refresh_projects_callback(callback: types.CallbackQuery):
    # Просто вызываем my_projects_callback снова
    await my_projects_callback(callback)

# Обработчик ошибок
@dp.error()
async def error_handler(event: types.ErrorEvent):
    logger.error(f"Error in handler: {event.exception}")
    
    if event.update.message:
        await event.update.message.answer(
            "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору."
        )

# Запуск бота
async def main():
    logger.info("Starting bot...")
    
    # Удаляем вебхук если был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())