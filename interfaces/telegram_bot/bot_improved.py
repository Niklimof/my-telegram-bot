# interfaces/telegram_bot/bot_improved.py
# Улучшенный Telegram бот с отображением процессов и созданием планов

import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import json

from config.settings import settings
from database.crud import create_project, get_plans, get_default_settings, get_project, create_plan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

# ===== СОСТОЯНИЯ =====
class VideoStates(StatesGroup):
    waiting_for_url = State()
    selecting_plan = State()

class PlanCreationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    selecting_base_prompt = State()
    editing_prompt = State()
    selecting_voice = State()
    selecting_emotion = State()
    selecting_speed = State()
    confirming_plan = State()

# ===== ХРАНИЛИЩА =====
# Активные процессы: {user_id: {project_id: process_data}}
active_processes = {}

# Проекты пользователей
user_projects = {}

# Временные данные создания плана
plan_drafts = {}

# ===== ЭМОДЗИ И СТАТУСЫ =====
STAGE_EMOJIS = {
    "waiting": "⏳",
    "downloading": "📥",
    "transcribing": "📝",
    "processing": "🤖",
    "generating_speech": "🎙",
    "uploading": "☁️",
    "completed": "✅",
    "failed": "❌"
}

STAGE_NAMES = {
    "waiting": "Ожидание",
    "downloading": "Загрузка видео",
    "transcribing": "Транскрибация",
    "processing": "Обработка текста",
    "generating_speech": "Создание озвучки",
    "uploading": "Загрузка на диск",
    "completed": "Завершено",
    "failed": "Ошибка"
}

# ===== ГЛАВНОЕ МЕНЮ =====
def get_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📹 Новое видео", callback_data="new_video"),
        InlineKeyboardButton(text="📊 Мои процессы", callback_data="my_processes")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Планы", callback_data="plans_menu"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    )
    builder.row(
        InlineKeyboardButton(text="❓ Помощь", callback_data="help")
    )
    
    return builder.as_markup()

# ===== КОМАНДА START =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 *Добро пожаловать в YouTube Automation Bot!*\n\n"
        "Я помогу вам автоматизировать обработку видео:\n"
        "• Транскрибация и обработка текста\n"
        "• Создание озвучки по вашим сценариям\n"
        "• Загрузка результатов на Яндекс.Диск\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ===== ОТОБРАЖЕНИЕ ПРОЦЕССОВ =====
def format_process_status(project_id: str, process_data: Dict) -> str:
    """Форматирует статус процесса для отображения"""
    stages = [
        ("downloading", process_data.get("downloading", "waiting")),
        ("transcribing", process_data.get("transcribing", "waiting")),
        ("processing", process_data.get("processing", "waiting")),
        ("generating_speech", process_data.get("generating_speech", "waiting")),
        ("uploading", process_data.get("uploading", "waiting"))
    ]
    
    # Заголовок
    text = f"📌 *Проект:* `{project_id[:8]}...`\n"
    text += f"🔗 *URL:* {process_data.get('url', 'Неизвестно')}\n"
    text += f"📋 *План:* {process_data.get('plan_name', 'Стандартный')}\n\n"
    
    # Прогресс бар
    completed_stages = sum(1 for _, status in stages if status == "completed")
    total_stages = len(stages)
    progress = completed_stages / total_stages
    
    progress_bar = "["
    filled = int(progress * 20)
    progress_bar += "█" * filled + "░" * (20 - filled)
    progress_bar += f"] {int(progress * 100)}%"
    
    text += f"*Прогресс:* {progress_bar}\n\n"
    
    # Этапы
    text += "*Этапы обработки:*\n"
    for stage_key, status in stages:
        emoji = STAGE_EMOJIS.get(status, "⏳")
        name = STAGE_NAMES.get(stage_key, stage_key)
        
        # Добавляем время если есть
        time_info = ""
        if status == "completed" and f"{stage_key}_time" in process_data:
            time_info = f" ({process_data[f'{stage_key}_time']})"
        elif status == "processing":
            time_info = " (в процессе...)"
        
        text += f"{emoji} {name}{time_info}\n"
    
    # Дополнительная информация
    if process_data.get("current_info"):
        text += f"\n💬 {process_data['current_info']}"
    
    # Время начала
    if process_data.get("started_at"):
        text += f"\n\n🕐 Начато: {process_data['started_at']}"
    
    return text

@dp.callback_query(F.data == "my_processes")
async def show_my_processes(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id not in active_processes or not active_processes[user_id]:
        await callback.message.edit_text(
            "📊 *Активные процессы*\n\n"
            "У вас нет активных процессов обработки.\n"
            "Нажмите '📹 Новое видео' чтобы начать.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return
    
    # Показываем список процессов
    text = "📊 *Ваши активные процессы:*\n\n"
    
    builder = InlineKeyboardBuilder()
    
    for project_id, process_data in active_processes[user_id].items():
        status = process_data.get("status", "unknown")
        emoji = STAGE_EMOJIS.get(status, "❓")
        
        # Краткая информация
        short_url = process_data.get("url", "")[:30] + "..."
        button_text = f"{emoji} {short_url}"
        
        builder.row(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"process_{project_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_processes"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("process_"))
async def show_process_details(callback: CallbackQuery):
    project_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if user_id not in active_processes or project_id not in active_processes[user_id]:
        await callback.answer("Процесс не найден", show_alert=True)
        return
    
    process_data = active_processes[user_id][project_id]
    text = format_process_status(project_id, process_data)
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки управления
    if process_data.get("status") not in ["completed", "failed"]:
        builder.row(
            InlineKeyboardButton(text="⏸ Пауза", callback_data=f"pause_{project_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{project_id}")
        )
    
    if process_data.get("status") == "completed":
        builder.row(
            InlineKeyboardButton(
                text="📁 Открыть результаты",
                url=process_data.get("result_url", "https://disk.yandex.ru")
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{project_id}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="my_processes")
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ===== МЕНЮ ПЛАНОВ =====
@dp.callback_query(F.data == "plans_menu")
async def show_plans_menu(callback: CallbackQuery):
    plans = get_plans(is_active=True)
    
    text = "📋 *Управление планами обработки*\n\n"
    text += "Планы определяют, как будет обработан ваш контент.\n"
    text += "Вы можете использовать готовые планы или создать свой.\n\n"
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка создания нового плана
    builder.row(
        InlineKeyboardButton(text="➕ Создать новый план", callback_data="create_plan")
    )
    
    # Список существующих планов
    if plans:
        text += "*Доступные планы:*\n"
        for i, plan in enumerate(plans, 1):
            text += f"{i}. {plan.name}\n"
            builder.row(
                InlineKeyboardButton(
                    text=f"👁 {plan.name}",
                    callback_data=f"view_plan_{plan.id}"
                ),
                InlineKeyboardButton(
                    text="✏️",
                    callback_data=f"edit_plan_{plan.id}"
                )
            )
    
    builder.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ===== СОЗДАНИЕ ПЛАНА =====
@dp.callback_query(F.data == "create_plan")
async def start_plan_creation(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    # Инициализируем черновик плана
    plan_drafts[user_id] = {
        "name": "",
        "description": "",
        "prompt": "",
        "voice": "alena",
        "emotion": "neutral",
        "speed": 1.0,
        "created_by": user_id
    }
    
    await callback.message.edit_text(
        "🆕 *Создание нового плана*\n\n"
        "Шаг 1/6: Введите название плана\n"
        "Например: _Динамичные истории_ или _Образовательный контент_\n\n"
        "Отправьте /cancel для отмены",
        parse_mode="Markdown"
    )
    
    await state.set_state(PlanCreationStates.waiting_for_name)
    await callback.answer()

@dp.message(StateFilter(PlanCreationStates.waiting_for_name))
async def process_plan_name(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Создание плана отменено", reply_markup=get_main_menu())
        return
    
    user_id = message.from_user.id
    plan_drafts[user_id]["name"] = message.text
    
    await message.answer(
        f"✅ Название: *{message.text}*\n\n"
        "Шаг 2/6: Введите описание плана\n"
        "Опишите, для какого типа контента подходит этот план",
        parse_mode="Markdown"
    )
    
    await state.set_state(PlanCreationStates.waiting_for_description)

@dp.message(StateFilter(PlanCreationStates.waiting_for_description))
async def process_plan_description(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Создание плана отменено", reply_markup=get_main_menu())
        return
    
    user_id = message.from_user.id
    plan_drafts[user_id]["description"] = message.text
    
    # Показываем шаблоны промптов
    builder = InlineKeyboardBuilder()
    
    templates = [
        ("📖 Сторителлинг", "storytelling"),
        ("🎓 Образовательный", "educational"),
        ("⚡ Динамичный", "dynamic"),
        ("🎭 Развлекательный", "entertainment"),
        ("✍️ Свой промпт", "custom")
    ]
    
    for name, template_id in templates:
        builder.row(
            InlineKeyboardButton(text=name, callback_data=f"template_{template_id}")
        )
    
    await message.answer(
        "Шаг 3/6: Выберите базовый шаблон промпта\n\n"
        "Вы сможете отредактировать его на следующем шаге",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.selecting_base_prompt)

# Шаблоны промптов
PROMPT_TEMPLATES = {
    "storytelling": """Перепиши этот текст в формате захватывающей истории. 
Добавь интригу, эмоциональные моменты, сделай повествование более личным и вовлекающим. 
Используй приемы сторителлинга: завязка, развитие, кульминация. 
Добавь диалоги, описания, детали. Расширь до 20000 слов.""",
    
    "educational": """Адаптируй этот текст для образовательного контента. 
Структурируй информацию логично, выдели ключевые моменты, добавь примеры, 
аналогии и объяснения для лучшего понимания. Раздели на тематические блоки. 
Добавь практические советы и выводы. Целевой объем - 20000 слов.""",
    
    "dynamic": """Перепиши этот текст в более динамичном и энергичном стиле. 
Сократи паузы, добавь эмоций, сделай речь более живой и захватывающей. 
Сохрани все важные факты и основной смысл. Расширь текст добавляя интересные детали, 
примеры и объяснения. Целевой объем - примерно 20000 слов.""",
    
    "entertainment": """Перепиши текст в развлекательном стиле. 
Добавь юмор где уместно, интересные факты, неожиданные повороты. 
Сделай текст легким для восприятия, но информативным. 
Используй яркие метафоры и сравнения. Расширь с интересными отступлениями до 20000 слов."""
}

@dp.callback_query(F.data.startswith("template_"))
async def select_prompt_template(callback: CallbackQuery, state: FSMContext):
    template_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if template_id == "custom":
        prompt = "Напишите свой промпт для обработки текста"
    else:
        prompt = PROMPT_TEMPLATES.get(template_id, "")
    
    plan_drafts[user_id]["prompt"] = prompt
    
    await callback.message.edit_text(
        f"Шаг 4/6: Отредактируйте промпт\n\n"
        f"*Текущий промпт:*\n```\n{prompt}\n```\n\n"
        f"Отправьте отредактированный текст или /skip чтобы оставить как есть",
        parse_mode="Markdown"
    )
    
    await state.set_state(PlanCreationStates.editing_prompt)
    await callback.answer()

@dp.message(StateFilter(PlanCreationStates.editing_prompt))
async def process_prompt_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text != "/skip":
        plan_drafts[user_id]["prompt"] = message.text
    
    # Выбор голоса
    builder = InlineKeyboardBuilder()
    
    voices = [
        ("👩 Алёна", "alena"),
        ("👨 Филипп", "filipp"),
        ("👨 Ермил", "ermil"),
        ("👩 Джейн", "jane"),
        ("👨 Мадирус", "madirus"),
        ("👩 Омаж", "omazh"),
        ("👨 Захар", "zahar")
    ]
    
    for name, voice_id in voices:
        builder.row(
            InlineKeyboardButton(text=name, callback_data=f"voice_{voice_id}")
        )
    
    await message.answer(
        "Шаг 5/6: Выберите голос для озвучки",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.selecting_voice)

@dp.callback_query(F.data.startswith("voice_"))
async def select_voice(callback: CallbackQuery, state: FSMContext):
    voice_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    plan_drafts[user_id]["voice"] = voice_id
    
    # Выбор эмоции
    builder = InlineKeyboardBuilder()
    
    emotions = [
        ("😐 Нейтральная", "neutral"),
        ("😊 Радостная", "good"),
        ("😠 Раздраженная", "evil")
    ]
    
    for name, emotion_id in emotions:
        builder.row(
            InlineKeyboardButton(text=name, callback_data=f"emotion_{emotion_id}")
        )
    
    await callback.message.edit_text(
        "Шаг 6/6: Выберите эмоцию голоса",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.selecting_emotion)
    await callback.answer()

@dp.callback_query(F.data.startswith("emotion_"))
async def select_emotion_and_confirm(callback: CallbackQuery, state: FSMContext):
    emotion_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    plan_drafts[user_id]["emotion"] = emotion_id
    
    # Показываем итоговый план для подтверждения
    plan = plan_drafts[user_id]
    
    text = "📋 *Проверьте ваш план:*\n\n"
    text += f"*Название:* {plan['name']}\n"
    text += f"*Описание:* {plan['description']}\n"
    text += f"*Голос:* {plan['voice']}\n"
    text += f"*Эмоция:* {plan['emotion']}\n\n"
    text += f"*Промпт:*\n```\n{plan['prompt'][:500]}...\n```"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить план", callback_data="save_plan"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_plan")
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(PlanCreationStates.confirming_plan)
    await callback.answer()

@dp.callback_query(F.data == "save_plan")
async def save_plan(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    plan_data = plan_drafts[user_id]
    
    # Создаем структуру плана для БД
    plan_dict = {
        "name": plan_data["name"],
        "description": plan_data["description"],
        "text_steps": [
            {
                "type": "extract_audio",
                "params": {"format": "mp3"}
            },
            {
                "type": "transcribe",
                "params": {
                    "language": "ru",
                    "model": "medium"
                }
            },
            {
                "type": "process_with_claude",
                "params": {
                    "prompt": plan_data["prompt"],
                    "model": "claude-3-sonnet-20240229",
                    "temperature": 0.7
                }
            },
            {
                "type": "generate_speech",
                "params": {
                    "voice": plan_data["voice"],
                    "emotion": plan_data["emotion"],
                    "speed": plan_data.get("speed", 1.0)
                }
            }
        ],
        "video_steps": [],
        "default_prompt": plan_data["prompt"],
        "default_voice": plan_data["voice"],
        "is_active": True,
        "modules_enabled": ["text"]
    }
    
    try:
        # Сохраняем в БД
        new_plan = create_plan(plan_dict)
        
        await callback.message.edit_text(
            f"✅ *План успешно создан!*\n\n"
            f"Название: {plan_data['name']}\n"
            f"Теперь вы можете использовать его для обработки видео.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        
        # Очищаем черновик
        del plan_drafts[user_id]
        
    except Exception as e:
        logger.error(f"Ошибка создания плана: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при создании плана. Попробуйте позже.",
            reply_markup=get_main_menu()
        )
    
    await state.clear()
    await callback.answer()

# ===== ОБРАБОТКА ВИДЕО =====
@dp.callback_query(F.data == "new_video")
async def new_video_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📹 *Новая обработка видео*\n\n"
        "Отправьте ссылку на YouTube видео:\n\n"
        "Поддерживаемые форматы:\n"
        "• `https://youtube.com/watch?v=...`\n"
        "• `https://youtu.be/...`\n"
        "• `https://m.youtube.com/watch?v=...`",
        parse_mode="Markdown"
    )
    await state.set_state(VideoStates.waiting_for_url)
    await callback.answer()

@dp.message(StateFilter(VideoStates.waiting_for_url))
async def process_url(message: types.Message, state: FSMContext):
    url = message.text
    
    # Валидация URL
    if not any(domain in url for domain in ["youtube.com", "youtu.be", "m.youtube.com"]):
        await message.answer(
            "❌ Пожалуйста, отправьте корректную ссылку на YouTube видео\n"
            "Пример: `https://youtube.com/watch?v=dQw4w9WgXcQ`",
            parse_mode="Markdown"
        )
        return
    
    # Сохраняем URL
    await state.update_data(youtube_url=url)
    
    # Получаем планы
    plans = get_plans(is_active=True)
    
    if not plans:
        await message.answer(
            "❌ Нет доступных планов обработки.\n"
            "Создайте план в меню '📋 Планы'",
            reply_markup=get_main_menu()
        )
        await state.clear()
        return
    
    # Показываем планы для выбора
    builder = InlineKeyboardBuilder()
    
    for plan in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"📋 {plan.name}",
                callback_data=f"select_plan_{plan.id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    await message.answer(
        "📋 *Выберите план обработки:*",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(VideoStates.selecting_plan)

@dp.callback_query(F.data.startswith("select_plan_"))
async def select_plan_callback(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    user_id = callback.from_user.id
    
    # Создаем проект
    project_id = str(uuid.uuid4())[:8]  # Короткий ID для удобства
    
    # Добавляем в активные процессы
    if user_id not in active_processes:
        active_processes[user_id] = {}
    
    active_processes[user_id][project_id] = {
        "url": data["youtube_url"],
        "plan_id": plan_id,
        "plan_name": get_plan_name(plan_id),
        "status": "waiting",
        "started_at": datetime.now().strftime("%H:%M"),
        "downloading": "waiting",
        "transcribing": "waiting",
        "processing": "waiting",
        "generating_speech": "waiting",
        "uploading": "waiting"
    }
    
    await callback.message.edit_text(
        f"✅ *Проект создан!*\n"
        f"ID: `{project_id}`\n\n"
        f"🚀 Обработка началась!\n\n"
        f"Вы можете следить за прогрессом в разделе '📊 Мои процессы'",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    
    # Запускаем обработку (имитация для демонстрации)
    asyncio.create_task(simulate_processing(user_id, project_id))
    
    await state.clear()
    await callback.answer()

# ===== СИМУЛЯЦИЯ ОБРАБОТКИ =====
async def simulate_processing(user_id: int, project_id: str):
    """Симулирует процесс обработки для демонстрации UI"""
    stages = [
        ("downloading", "Загружаю видео...", 5),
        ("transcribing", "Транскрибирую аудио...", 8),
        ("processing", "Обрабатываю текст через AI...", 10),
        ("generating_speech", "Создаю озвучку...", 12),
        ("uploading", "Загружаю на Яндекс.Диск...", 5)
    ]
    
    for stage, info, duration in stages:
        # Обновляем статус
        if user_id in active_processes and project_id in active_processes[user_id]:
            active_processes[user_id][project_id]["status"] = stage
            active_processes[user_id][project_id][stage] = "processing"
            active_processes[user_id][project_id]["current_info"] = info
            
            # Ждем
            await asyncio.sleep(duration)
            
            # Отмечаем как завершенное
            active_processes[user_id][project_id][stage] = "completed"
            active_processes[user_id][project_id][f"{stage}_time"] = f"{duration}с"
    
    # Финальный статус
    if user_id in active_processes and project_id in active_processes[user_id]:
        active_processes[user_id][project_id]["status"] = "completed"
        active_processes[user_id][project_id]["current_info"] = "Обработка завершена!"
        active_processes[user_id][project_id]["result_url"] = "https://disk.yandex.ru/example"
        
        # Отправляем уведомление
        try:
            await bot.send_message(
                user_id,
                f"✅ *Обработка завершена!*\n\n"
                f"Проект: `{project_id}`\n"
                f"[Открыть результаты](https://disk.yandex.ru/example)",
                parse_mode="Markdown"
            )
        except:
            pass

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def get_plan_name(plan_id: int) -> str:
    """Получает название плана по ID"""
    try:
        from database.crud import get_plan
        plan = get_plan(plan_id)
        return plan.name if plan else "Неизвестный план"
    except:
        return "Стандартный"

# ===== ОБРАБОТЧИКИ КНОПОК =====
@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "👋 *Главное меню*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "refresh_processes")
async def refresh_processes(callback: CallbackQuery):
    await show_my_processes(callback)

@dp.callback_query(F.data.startswith("refresh_"))
async def refresh_process(callback: CallbackQuery):
    # Обновляем конкретный процесс
    await show_process_details(callback)

@dp.callback_query(F.data.startswith("pause_"))
async def pause_process(callback: CallbackQuery):
    project_id = callback.data.split("_")[1]
    await callback.answer("⏸ Функция паузы будет доступна в следующей версии", show_alert=True)

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_process(callback: CallbackQuery):
    project_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if user_id in active_processes and project_id in active_processes[user_id]:
        active_processes[user_id][project_id]["status"] = "failed"
        active_processes[user_id][project_id]["current_info"] = "Отменено пользователем"
    
    await callback.answer("❌ Процесс отменен", show_alert=True)
    await show_process_details(callback)

@dp.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ *Настройки*\n\n"
        "Этот раздел находится в разработке.\n"
        "Здесь вы сможете:\n"
        "• Настроить уведомления\n"
        "• Изменить параметры по умолчанию\n"
        "• Управлять интеграциями",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    help_text = """
❓ *Помощь по использованию бота*

*📹 Обработка видео:*
1. Нажмите "Новое видео"
2. Отправьте ссылку на YouTube
3. Выберите план обработки
4. Следите за прогрессом в "Мои процессы"

*📋 Создание планов:*
1. Перейдите в "Планы"
2. Нажмите "Создать новый план"
3. Следуйте пошаговой инструкции
4. Настройте промпт и параметры озвучки

*📊 Отслеживание процессов:*
• Все активные обработки отображаются в реальном времени
• Вы можете видеть статус каждого этапа
• По завершении получите ссылку на результаты

*💡 Советы:*
• Используйте разные планы для разных типов контента
• Промпты можно адаптировать под ваши нужды
• Обработка длинных видео может занять время

*🆘 Поддержка:*
Если у вас возникли проблемы, обратитесь к администратору.
"""
    
    await callback.message.edit_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("view_plan_"))
async def view_plan_details(callback: CallbackQuery):
    plan_id = int(callback.data.split("_")[2])
    
    try:
        from database.crud import get_plan
        plan = get_plan(plan_id)
        
        if not plan:
            await callback.answer("План не найден", show_alert=True)
            return
        
        # Извлекаем информацию о промпте
        claude_step = next(
            (step for step in plan.text_steps if step["type"] == "process_with_claude"),
            None
        )
        
        speech_step = next(
            (step for step in plan.text_steps if step["type"] == "generate_speech"),
            None
        )
        
        text = f"📋 *План: {plan.name}*\n\n"
        text += f"*Описание:* {plan.description}\n\n"
        
        if claude_step:
            prompt = claude_step["params"].get("prompt", "Не указан")
            text += f"*Промпт для обработки:*\n```\n{prompt[:800]}{'...' if len(prompt) > 800 else ''}\n```\n\n"
        
        if speech_step:
            text += f"*Параметры озвучки:*\n"
            text += f"• Голос: {speech_step['params'].get('voice', 'alena')}\n"
            text += f"• Эмоция: {speech_step['params'].get('emotion', 'neutral')}\n"
            text += f"• Скорость: {speech_step['params'].get('speed', 1.0)}\n"
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_plan_{plan_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_plan_{plan_id}")
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="plans_menu")
        )
        
        await callback.message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка просмотра плана: {e}")
        await callback.answer("Ошибка при загрузке плана", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_plan_"))
async def edit_plan(callback: CallbackQuery):
    await callback.answer("✏️ Редактирование планов будет доступно в следующей версии", show_alert=True)

@dp.callback_query(F.data.startswith("delete_plan_"))
async def delete_plan(callback: CallbackQuery):
    await callback.answer("🗑 Удаление планов будет доступно в следующей версии", show_alert=True)

# ===== ОБРАБОТЧИК ОШИБОК =====
@dp.error()
async def error_handler(event: types.ErrorEvent):
    logger.error(f"Error in handler: {event.exception}")
    
    if event.update.message:
        await event.update.message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_menu()
        )

# ===== ЗАПУСК БОТА =====
async def main():
    logger.info("Starting improved bot...")
    
    # Удаляем вебхук если был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())