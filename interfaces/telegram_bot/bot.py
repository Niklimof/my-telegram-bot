# interfaces/telegram_bot/improved_bot.py
# Улучшенная версия бота с интерфейсом создания и выбора планов

import asyncio
import logging
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uuid
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from database.crud import (
    create_project, get_plans, get_default_settings, 
    get_project, create_plan, get_plan
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Безопасная инициализация бота
if not settings.TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN не установлен!")
    raise ValueError("Необходимо установить TELEGRAM_TOKEN в .env файле")

bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

# ===== СОСТОЯНИЯ =====
class VideoStates(StatesGroup):
    waiting_for_url = State()
    selecting_plan = State()

class PlanCreationStates(StatesGroup):
    entering_name = State()
    entering_description = State()
    selecting_type = State()
    entering_custom_prompt = State()
    entering_voice_settings = State()
    reviewing_plan = State()

# ===== КОНСТАНТЫ =====
# Целевое количество слов для 80-100 минут видео
TARGET_WORDS = 13500  # Среднее между 12000-15000

# Шаблоны планов
PLAN_TEMPLATES = {
    "horror_story": {
        "name": "🎃 Мистический рассказ",
        "description": "Превращает видео в захватывающую историю ужасов",
        "prompt_template": """На основе этого текста создай детальный план мистического рассказа.

ТРЕБОВАНИЯ К ПЛАНУ:
1. Жанр: психологический хоррор с элементами мистики
2. Структура: 3 акта с нарастающим напряжением
3. Объем: план на {target_words} слов (~90 минут аудио)
4. Атмосфера: зловещая, тревожная, с нарастающей паранойей

СТРУКТУРА ПЛАНА:
- Название рассказа
- Основная идея и твист
- Главные персонажи (3-4) с характерами
- АКТ 1: Экспозиция (25%) - обычная жизнь с тревожными деталями
- АКТ 2: Развитие (50%) - эскалация странных событий
- АКТ 3: Кульминация (25%) - разрешение и шокирующий финал
- Ключевые сцены (10-12) с описанием
- Атмосферные детали и символы

Исходный материал:
{text}"""
    },
    
    "educational_story": {
        "name": "📚 Образовательная история",
        "description": "Превращает информацию в увлекательный обучающий рассказ",
        "prompt_template": """Преобразуй этот материал в план увлекательного образовательного рассказа.

ТРЕБОВАНИЯ:
1. Формат: история-путешествие с элементами приключения
2. Цель: обучение через погружение в историю
3. Объем: план на {target_words} слов
4. Стиль: динамичный, с диалогами и примерами

СТРУКТУРА ПЛАНА:
- Название и образовательная цель
- Главный герой (исследователь/ученый/журналист)
- Квест или миссия героя
- Этапы путешествия (соответствуют темам из материала)
- Препятствия и их преодоление
- Встречи с экспертами (диалоги)
- Открытия и озарения
- Практическое применение знаний
- Вдохновляющий финал

Исходный материал:
{text}"""
    },
    
    "personal_story": {
        "name": "💭 Личная история",
        "description": "Создает эмоциональный рассказ от первого лица",
        "prompt_template": """Создай план личной истории на основе этого материала.

ТРЕБОВАНИЯ:
1. Повествование от первого лица
2. Эмоциональная глубина и искренность
3. Объем: план на {target_words} слов
4. Фокус на личном опыте и переживаниях

СТРУКТУРА:
- Название и основной конфликт
- Герой-рассказчик (детальный портрет)
- Начальная ситуация
- Катализатор изменений
- Путь трансформации (5-7 этапов)
- Внутренние конфликты и сомнения
- Поддерживающие персонажи
- Кульминационный выбор
- Новое понимание и рост
- Послание читателю

Материал для адаптации:
{text}"""
    }
}

# Хранилище активных проектов
user_projects = {}
plan_creation_data = {}

# ===== ОСНОВНЫЕ КОМАНДЫ =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Новое видео", callback_data="new_video")],
        [InlineKeyboardButton(text="📋 Управление планами", callback_data="manage_plans")],
        [InlineKeyboardButton(text="📊 Мои проекты", callback_data="my_projects")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    await message.answer(
        "👋 Привет! Я помогу превратить YouTube видео в увлекательные рассказы.\n\n"
        "🎯 Что я умею:\n"
        "• Скачиваю видео и извлекаю текст\n"
        "• Создаю из него захватывающий рассказ (80-100 минут)\n"
        "• Озвучиваю через Yandex SpeechKit\n"
        "• Сохраняю на Яндекс.Диск\n\n"
        "🎨 Использую двойную обработку Claude AI для максимального качества\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

# ===== УПРАВЛЕНИЕ ПЛАНАМИ =====
@dp.callback_query(lambda c: c.data == "manage_plans")
async def manage_plans_callback(callback: CallbackQuery):
    plans = get_plans(is_active=True)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать новый план", callback_data="create_plan")],
        [InlineKeyboardButton(text="📋 Список планов", callback_data="list_plans")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"📋 *Управление планами обработки*\n\n"
        f"Активных планов: {len(plans)}\n\n"
        f"Планы определяют, как видео превращается в рассказ",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "create_plan")
async def create_plan_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    plan_creation_data[user_id] = {}
    
    await callback.message.edit_text(
        "📝 *Создание нового плана*\n\n"
        "Шаг 1/5: Введите название плана\n\n"
        "Например: _Мистические истории_ или _Образовательные приключения_",
        parse_mode="Markdown"
    )
    
    await state.set_state(PlanCreationStates.entering_name)
    await callback.answer()

@dp.message(PlanCreationStates.entering_name)
async def process_plan_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    plan_creation_data[user_id]["name"] = message.text
    
    await message.answer(
        f"✅ Название: *{message.text}*\n\n"
        f"Шаг 2/5: Введите описание плана\n\n"
        f"Опишите, для каких видео подходит этот план:",
        parse_mode="Markdown"
    )
    
    await state.set_state(PlanCreationStates.entering_description)

@dp.message(PlanCreationStates.entering_description)
async def process_plan_description(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    plan_creation_data[user_id]["description"] = message.text
    
    # Показываем типы планов
    builder = InlineKeyboardBuilder()
    
    for template_id, template_info in PLAN_TEMPLATES.items():
        builder.row(
            InlineKeyboardButton(
                text=template_info["name"],
                callback_data=f"template_{template_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="✏️ Свой промпт",
            callback_data="custom_prompt"
        )
    )
    
    await message.answer(
        "Шаг 3/5: Выберите тип плана\n\n"
        "Это определит, как будет обрабатываться текст:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.selecting_type)

@dp.callback_query(lambda c: c.data.startswith("template_"))
async def process_template_selection(callback: CallbackQuery, state: FSMContext):
    template_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    template = PLAN_TEMPLATES[template_id]
    plan_creation_data[user_id]["template"] = template_id
    plan_creation_data[user_id]["prompt_template"] = template["prompt_template"]
    
    # Настройки голоса
    builder = InlineKeyboardBuilder()
    voices = {
        "alena": "👩 Алёна (нейтральный)",
        "jane": "👩 Джейн (эмоциональный)",
        "omazh": "👨 Омаж (мужской)"
    }
    
    for voice_id, voice_name in voices.items():
        builder.row(
            InlineKeyboardButton(
                text=voice_name,
                callback_data=f"voice_{voice_id}"
            )
        )
    
    await callback.message.edit_text(
        f"Выбран шаблон: *{template['name']}*\n\n"
        f"Шаг 4/5: Выберите голос для озвучки:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.entering_voice_settings)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "custom_prompt")
async def custom_prompt_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ *Свой промпт для первого Claude*\n\n"
        "Введите промпт, который будет использоваться для создания плана рассказа.\n\n"
        "Используйте переменные:\n"
        "• `{text}` - транскрипция видео\n"
        "• `{target_words}` - целевое количество слов\n\n"
        "Отправьте промпт следующим сообщением:",
        parse_mode="Markdown"
    )
    
    await state.set_state(PlanCreationStates.entering_custom_prompt)
    await callback.answer()

@dp.message(PlanCreationStates.entering_custom_prompt)
async def process_custom_prompt(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    plan_creation_data[user_id]["prompt_template"] = message.text
    plan_creation_data[user_id]["template"] = "custom"
    
    # Переходим к выбору голоса
    builder = InlineKeyboardBuilder()
    voices = {
        "alena": "👩 Алёна",
        "jane": "👩 Джейн", 
        "omazh": "👨 Омаж"
    }
    
    for voice_id, voice_name in voices.items():
        builder.row(
            InlineKeyboardButton(
                text=voice_name,
                callback_data=f"voice_{voice_id}"
            )
        )
    
    await message.answer(
        "Шаг 4/5: Выберите голос для озвучки:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.entering_voice_settings)

@dp.callback_query(lambda c: c.data.startswith("voice_"))
async def process_voice_selection(callback: CallbackQuery, state: FSMContext):
    voice_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    plan_creation_data[user_id]["voice"] = voice_id
    
    # Показываем финальный обзор
    data = plan_creation_data[user_id]
    
    review_text = f"""📋 *Обзор нового плана*

*Название:* {data['name']}
*Описание:* {data['description']}
*Тип:* {PLAN_TEMPLATES.get(data.get('template', 'custom'), {}).get('name', 'Пользовательский')}
*Голос:* {voice_id}
*Целевой объем:* {TARGET_WORDS} слов (~90 минут)

Сохранить план?"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить", callback_data="save_plan"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_plan")
    )
    
    await callback.message.edit_text(
        review_text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.reviewing_plan)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "save_plan")
async def save_plan_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = plan_creation_data[user_id]
    
    # Создаем структуру плана с двумя диалогами Claude
    plan_data = {
        "name": data["name"],
        "description": data["description"],
        "text_steps": [
            {
                "type": "extract_audio",
                "params": {"format": "mp3"}
            },
            {
                "type": "transcribe",
                "params": {
                    "language": "ru",
                    "model": "large"  # Используем large для лучшего качества
                }
            },
            {
                "type": "create_story_plan",  # Первый Claude
                "params": {
                    "prompt": data["prompt_template"],
                    "model": "claude-3-sonnet-20240229",
                    "temperature": 0.7,
                    "target_words": TARGET_WORDS
                }
            },
            {
                "type": "write_story",  # Второй Claude
                "params": {
                    "model": "claude-3-sonnet-20240229",
                    "temperature": 0.8,
                    "target_words": TARGET_WORDS
                }
            },
            {
                "type": "generate_speech",
                "params": {
                    "voice": data["voice"],
                    "emotion": "neutral",
                    "speed": 1.0
                }
            }
        ],
        "video_steps": [],
        "default_prompt": data["prompt_template"],
        "default_voice": data["voice"],
        "is_active": True,
        "modules_enabled": ["text"],
        "metadata": {
            "target_words": TARGET_WORDS,
            "template": data.get("template", "custom")
        }
    }
    
    # Сохраняем в БД
    plan = create_plan(plan_data)
    
    await callback.message.edit_text(
        f"✅ План *{data['name']}* успешно создан!\n\n"
        f"ID плана: `{plan.id}`\n\n"
        f"Теперь вы можете использовать его для обработки видео.",
        parse_mode="Markdown"
    )
    
    # Очищаем временные данные
    del plan_creation_data[user_id]
    await state.clear()
    
    # Показываем главное меню
    await asyncio.sleep(2)
    await cmd_start(callback.message)
    await callback.answer()

# ===== ОБРАБОТКА ВИДЕО =====
@dp.callback_query(lambda c: c.data == "new_video")
async def new_video_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
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
            "❌ Пожалуйста, отправьте корректную ссылку на YouTube видео"
        )
        return
    
    # Сохраняем URL
    await state.update_data(youtube_url=url)
    
    # Получаем активные планы
    plans = get_plans(is_active=True)
    
    if not plans:
        await message.answer(
            "❌ Нет доступных планов обработки.\n"
            "Создайте план через меню 'Управление планами'."
        )
        await state.clear()
        return
    
    # Если план только один - используем его автоматически
    if len(plans) == 1:
        plan = plans[0]
        await message.answer(
            f"📋 Используется единственный доступный план: *{plan.name}*\n\n"
            f"🚀 Запускаю обработку...",
            parse_mode="Markdown"
        )
        
        # Создаем проект
        await create_and_start_project(message, state, plan.id, url)
        return
    
    # Если планов несколько - показываем выбор
    keyboard_buttons = []
    for plan in plans:
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
        "📋 Выберите план обработки:",
        reply_markup=keyboard
    )
    await state.set_state(VideoStates.selecting_plan)

async def create_and_start_project(message: types.Message, state: FSMContext, plan_id: int, url: str):
    """Создает проект и запускает обработку"""
    
    # Создаем проект
    project_id = str(uuid.uuid4())
    settings_obj = get_default_settings()
    
    project = create_project({
        "id": project_id,
        "youtube_url": url,
        "plan_id": plan_id,
        "settings_id": settings_obj.id if settings_obj else 1,
        "telegram_user_id": message.from_user.id,
        "telegram_chat_id": message.chat.id,
        "phase": 1,
        "status": "created"
    })
    
    # Сохраняем проект для пользователя
    user_id = message.from_user.id
    if user_id not in user_projects:
        user_projects[user_id] = []
    user_projects[user_id].append(project_id)
    
    await message.answer(
        f"✅ Проект создан!\n"
        f"ID: `{project_id}`\n\n"
        f"🚀 Запускаю обработку...\n\n"
        f"⏱ Примерное время: 80-100 минут\n"
        f"📊 Вы получите уведомления о прогрессе",
        parse_mode="Markdown"
    )
    
    # Запускаем обработку через Celery
    try:
        from workers.tasks.text_tasks import process_text_pipeline
        process_text_pipeline.delay(project_id)
        logger.info(f"Задача отправлена в Celery для проекта {project_id}")
    except Exception as e:
        logger.error(f"Ошибка при запуске задачи: {e}")
        await message.answer(
            "❌ Произошла ошибка при запуске обработки."
        )
    
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("plan_"))
async def select_plan_callback(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    
    plan = get_plan(plan_id)
    await callback.message.edit_text(
        f"📋 Выбран план: *{plan.name}*\n\n"
        f"🚀 Запускаю обработку...",
        parse_mode="Markdown"
    )
    
    # Создаем проект
    await create_and_start_project(callback.message, state, plan_id, data["youtube_url"])
    await callback.answer()

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
@dp.callback_query(lambda c: c.data == "list_plans")
async def list_plans_callback(callback: CallbackQuery):
    plans = get_plans(is_active=True)
    
    if not plans:
        await callback.message.edit_text(
            "📋 Нет активных планов.\n\n"
            "Создайте новый план для начала работы."
        )
        await callback.answer()
        return
    
    text = "📋 *Активные планы:*\n\n"
    
    for i, plan in enumerate(plans, 1):
        text += f"{i}. *{plan.name}*\n"
        text += f"   _{plan.description}_\n"
        
        # Показываем метаданные если есть
        if plan.metadata:
            template = plan.metadata.get("template", "custom")
            if template in PLAN_TEMPLATES:
                text += f"   Тип: {PLAN_TEMPLATES[template]['name']}\n"
        
        text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать новый", callback_data="create_plan")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Операция отменена")
    await cmd_start(callback.message)
    await callback.answer()

# ===== ОБРАБОТЧИК ОШИБОК =====
@dp.error()
async def error_handler(event: types.ErrorEvent):
    logger.error(f"Error in handler: {event.exception}")
    
    if event.update.message:
        await event.update.message.answer(
            "❌ Произошла ошибка. Попробуйте позже."
        )

# ===== ФУНКЦИЯ ДЛЯ УВЕДОМЛЕНИЙ =====
async def notify_progress(chat_id: int, project_id: str, message: str):
    """Отправляет уведомление о прогрессе обработки"""
    try:
        await bot.send_message(
            chat_id,
            f"📊 Проект `{project_id[:8]}...`\n{message}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")

# ===== ЗАПУСК БОТА =====
async def main():
    logger.info("Starting improved bot...")
    
    # Удаляем вебхук если был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())