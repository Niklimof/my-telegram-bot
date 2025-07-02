# interfaces/telegram_bot/advanced_plan_creator.py
# Продвинутый конструктор планов для создания рассказов

import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import json
from typing import Dict, List, Optional

# ===== СОСТОЯНИЯ ДЛЯ СОЗДАНИЯ ПЛАНА =====
class AdvancedPlanStates(StatesGroup):
    # Основная информация
    selecting_genre = State()
    selecting_subgenre = State()
    selecting_audience = State()
    entering_name = State()
    entering_description = State()
    
    # Структура
    selecting_structure = State()
    customizing_acts = State()
    
    # Атмосфера и стиль
    selecting_atmosphere = State()
    selecting_narrative_style = State()
    
    # Технические детали
    selecting_word_count = State()
    configuring_voice = State()
    adding_special_instructions = State()
    
    # Финализация
    reviewing_plan = State()
    saving_plan = State()

# ===== ШАБЛОНЫ И ОПЦИИ =====

GENRES = {
    "horror": {
        "name": "🎃 Ужасы",
        "subgenres": ["Психологический хоррор", "Мистика", "Городские легенды", "Паранормальное"],
        "atmospheres": ["Напряженная", "Зловещая", "Тревожная", "Гнетущая"],
        "elements": ["Саспенс", "Внезапные повороты", "Нарастающий страх", "Жуткие детали"]
    },
    "detective": {
        "name": "🔍 Детектив",
        "subgenres": ["Классический", "Нуар", "Психологический", "Криминальный"],
        "atmospheres": ["Загадочная", "Напряженная", "Интригующая"],
        "elements": ["Улики", "Подозреваемые", "Расследование", "Разоблачение"]
    },
    "drama": {
        "name": "🎭 Драма",
        "subgenres": ["Семейная", "Социальная", "Психологическая", "Романтическая"],
        "atmospheres": ["Эмоциональная", "Трогательная", "Напряженная"],
        "elements": ["Конфликты", "Развитие персонажей", "Эмоции", "Отношения"]
    },
    "fantasy": {
        "name": "🧙 Фэнтези",
        "subgenres": ["Эпическое", "Городское", "Темное", "Сказочное"],
        "atmospheres": ["Волшебная", "Таинственная", "Эпическая"],
        "elements": ["Магия", "Квесты", "Мифические существа", "Другие миры"]
    }
}

AUDIENCES = {
    "general": "👥 Общая аудитория",
    "male_25_45": "👨 Мужчины 25-45 лет",
    "female_25_45": "👩 Женщины 25-45 лет",
    "young_adults": "🧑 Молодежь 18-25 лет",
    "mature": "👴👵 Взрослая аудитория 45+"
}

STRUCTURES = {
    "three_act": {
        "name": "📖 Классическая трехактная",
        "description": "Завязка (25%) → Развитие (50%) → Кульминация и развязка (25%)",
        "acts": ["Акт 1: Завязка", "Акт 2: Развитие", "Акт 3: Кульминация"]
    },
    "five_act": {
        "name": "📚 Пятиактная структура",
        "description": "Экспозиция → Развитие → Кульминация → Спад → Развязка",
        "acts": ["Экспозиция", "Развитие", "Кульминация", "Спад действия", "Развязка"]
    },
    "circular": {
        "name": "🔄 Циклическая",
        "description": "История возвращается к началу, но с новым пониманием",
        "acts": ["Начало", "Путешествие", "Откровение", "Возвращение"]
    },
    "nonlinear": {
        "name": "🔀 Нелинейная",
        "description": "События раскрываются не в хронологическом порядке",
        "acts": ["Настоящее", "Флешбеки", "Параллельные линии", "Объединение"]
    }
}

NARRATIVE_STYLES = {
    "first_person": "👤 От первого лица",
    "third_person": "👥 От третьего лица",
    "omniscient": "👁 Всезнающий рассказчик",
    "limited": "🔍 Ограниченная перспектива",
    "multiple": "🎭 Множественные рассказчики"
}

# ===== ХРАНИЛИЩЕ ПЛАНОВ В ПРОЦЕССЕ СОЗДАНИЯ =====
plan_drafts = {}

# ===== ФУНКЦИИ ДЛЯ СОЗДАНИЯ ПРОМПТОВ =====

def build_base_prompt(plan_data: Dict) -> str:
    """Создает базовый промпт на основе данных плана"""
    
    genre_info = GENRES.get(plan_data['genre'], {})
    structure_info = STRUCTURES.get(plan_data['structure'], {})
    
    prompt = f"""Создай {genre_info.get('name', 'рассказ')} в поджанре "{plan_data.get('subgenre', '')}" для аудитории: {AUDIENCES.get(plan_data['audience'], 'общая')}.

СТРУКТУРА: {structure_info.get('name', 'Трехактная')}
{structure_info.get('description', '')}

АТМОСФЕРА: {', '.join(plan_data.get('atmospheres', []))}

СТИЛЬ ПОВЕСТВОВАНИЯ: {NARRATIVE_STYLES.get(plan_data.get('narrative_style', 'third_person'))}

ОБЪЕМ: {plan_data.get('word_count', 20000)} слов

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. История должна захватывать с первых строк
2. Используй яркие описания и живые диалоги
3. Создавай напряжение и поддерживай интерес
4. Каждая сцена должна продвигать сюжет
5. Финал должен быть удовлетворительным и запоминающимся

ОСОБЫЕ УКАЗАНИЯ:
{plan_data.get('special_instructions', 'Нет дополнительных указаний')}

ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ ДЛЯ ОЗВУЧКИ:
- Разделяй текст на логические части
- Используй многоточия для пауз
- Выделяй важные моменты
- Диалоги должны звучать естественно
"""
    
    # Добавляем детальные инструкции по актам
    if plan_data.get('act_details'):
        prompt += "\n\nДЕТАЛЬНАЯ СТРУКТУРА ПО АКТАМ:\n"
        for act, details in plan_data['act_details'].items():
            prompt += f"\n{act}:\n{details}\n"
    
    return prompt

def build_act_instructions(genre: str, structure: str, act_number: int) -> str:
    """Создает инструкции для конкретного акта"""
    
    templates = {
        "horror": {
            "three_act": {
                1: """- Представь главного героя в обычной обстановке
- Создай тревожную атмосферу через детали
- Введи первый намек на сверхъестественное
- Закончи первым пугающим событием""",
                2: """- Эскалация странных событий
- Раскрытие истории места/проклятия
- Нарастание паранойи героя
- Серия пугающих столкновений
- Подготовка к финальной конфронтации""",
                3: """- Кульминационное столкновение со злом
- Раскрытие всех тайн
- Борьба за выживание
- Финальный твист или разрешение"""
            }
        },
        "detective": {
            "three_act": {
                1: """- Представление детектива
- Обнаружение преступления
- Первичный осмотр места происшествия
- Введение подозреваемых""",
                2: """- Сбор улик и допросы
- Ложные следы и тупики
- Углубление в мотивы персонажей
- Неожиданные открытия
- Сужение круга подозреваемых""",
                3: """- Финальная догадка детектива
- Сбор всех персонажей
- Драматическое разоблачение
- Объяснение метода преступления"""
            }
        }
    }
    
    return templates.get(genre, {}).get(structure, {}).get(act_number, "Развивай сюжет согласно жанру")

# ===== ИНТЕРФЕЙС СОЗДАНИЯ ПЛАНА =====

async def start_advanced_plan_creation(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания продвинутого плана"""
    
    user_id = callback.from_user.id
    plan_drafts[user_id] = {
        "creator_id": user_id,
        "genre": "",
        "subgenre": "",
        "audience": "",
        "name": "",
        "description": "",
        "structure": "",
        "atmospheres": [],
        "narrative_style": "",
        "word_count": 20000,
        "voice_settings": {},
        "special_instructions": "",
        "act_details": {}
    }
    
    # Показываем выбор жанра
    builder = InlineKeyboardBuilder()
    
    for genre_id, genre_info in GENRES.items():
        builder.row(
            InlineKeyboardButton(
                text=genre_info["name"],
                callback_data=f"genre_{genre_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_plan")
    )
    
    await callback.message.edit_text(
        "📚 *Создание профессионального плана для рассказа*\n\n"
        "Шаг 1/10: Выберите основной жанр\n\n"
        "Это определит базовую структуру и атмосферу вашего рассказа.",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.selecting_genre)
    await callback.answer()

async def process_genre_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор жанра"""
    
    genre_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    plan_drafts[user_id]["genre"] = genre_id
    genre_info = GENRES[genre_id]
    
    # Показываем поджанры
    builder = InlineKeyboardBuilder()
    
    for subgenre in genre_info["subgenres"]:
        builder.row(
            InlineKeyboardButton(
                text=subgenre,
                callback_data=f"subgenre_{subgenre}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_genre")
    )
    
    await callback.message.edit_text(
        f"Выбран жанр: *{genre_info['name']}*\n\n"
        "Шаг 2/10: Выберите поджанр\n\n"
        "Это поможет более точно настроить стиль повествования.",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.selecting_subgenre)
    await callback.answer()

async def process_subgenre_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор поджанра"""
    
    subgenre = callback.data.replace("subgenre_", "")
    user_id = callback.from_user.id
    
    plan_drafts[user_id]["subgenre"] = subgenre
    
    # Показываем выбор аудитории
    builder = InlineKeyboardBuilder()
    
    for audience_id, audience_name in AUDIENCES.items():
        builder.row(
            InlineKeyboardButton(
                text=audience_name,
                callback_data=f"audience_{audience_id}"
            )
        )
    
    await callback.message.edit_text(
        f"Поджанр: *{subgenre}*\n\n"
        "Шаг 3/10: Выберите целевую аудиторию\n\n"
        "Это повлияет на стиль изложения и выбор тем.",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.selecting_audience)
    await callback.answer()

async def process_audience_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор аудитории"""
    
    audience_id = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    
    plan_drafts[user_id]["audience"] = audience_id
    
    await callback.message.edit_text(
        f"Аудитория: *{AUDIENCES[audience_id]}*\n\n"
        "Шаг 4/10: Введите название плана\n\n"
        "Например: _Мистические истории для вечернего чтения_\n\n"
        "Отправьте название в следующем сообщении:",
        parse_mode="Markdown"
    )
    
    await state.set_state(AdvancedPlanStates.entering_name)
    await callback.answer()

async def process_plan_name(message: types.Message, state: FSMContext):
    """Обрабатывает название плана"""
    
    user_id = message.from_user.id
    plan_drafts[user_id]["name"] = message.text
    
    await message.answer(
        f"Название: *{message.text}*\n\n"
        "Шаг 5/10: Введите описание плана\n\n"
        "Опишите, для каких историй подходит этот план:",
        parse_mode="Markdown"
    )
    
    await state.set_state(AdvancedPlanStates.entering_description)

async def process_plan_description(message: types.Message, state: FSMContext):
    """Обрабатывает описание плана"""
    
    user_id = message.from_user.id
    plan_drafts[user_id]["description"] = message.text
    
    # Показываем выбор структуры
    builder = InlineKeyboardBuilder()
    
    for struct_id, struct_info in STRUCTURES.items():
        builder.row(
            InlineKeyboardButton(
                text=struct_info["name"],
                callback_data=f"structure_{struct_id}"
            )
        )
    
    await message.answer(
        "Шаг 6/10: Выберите структуру повествования\n\n"
        "Это определит, как будет развиваться сюжет:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.selecting_structure)

async def process_structure_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор структуры"""
    
    structure_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    plan_drafts[user_id]["structure"] = structure_id
    structure_info = STRUCTURES[structure_id]
    
    # Показываем информацию о структуре и переходим к настройке актов
    builder = InlineKeyboardBuilder()
    
    for i, act in enumerate(structure_info["acts"], 1):
        builder.row(
            InlineKeyboardButton(
                text=f"📝 Настроить {act}",
                callback_data=f"customize_act_{i}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="⏭ Пропустить настройку актов",
            callback_data="skip_acts"
        )
    )
    
    await callback.message.edit_text(
        f"Структура: *{structure_info['name']}*\n"
        f"_{structure_info['description']}_\n\n"
        "Шаг 7/10: Настройка актов (опционально)\n\n"
        "Вы можете детально настроить каждый акт или пропустить этот шаг:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.customizing_acts)
    await callback.answer()

async def customize_act(callback: CallbackQuery, state: FSMContext):
    """Показывает интерфейс настройки конкретного акта"""
    
    act_number = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    genre = plan_drafts[user_id]["genre"]
    structure = plan_drafts[user_id]["structure"]
    
    # Получаем шаблон инструкций для акта
    template = build_act_instructions(genre, structure, act_number)
    
    await callback.message.edit_text(
        f"*Настройка Акта {act_number}*\n\n"
        f"Рекомендуемая структура:\n```\n{template}\n```\n\n"
        "Отправьте свои инструкции для этого акта или /skip чтобы использовать рекомендуемые:",
        parse_mode="Markdown"
    )
    
    # Сохраняем номер акта в состоянии
    await state.update_data(current_act=act_number)
    await callback.answer()

async def process_atmosphere_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор атмосферы"""
    
    user_id = callback.from_user.id
    genre = plan_drafts[user_id]["genre"]
    
    # Показываем доступные атмосферы для жанра
    builder = InlineKeyboardBuilder()
    
    atmospheres = GENRES[genre].get("atmospheres", [])
    selected_atmospheres = plan_drafts[user_id].get("atmospheres", [])
    
    for atmosphere in atmospheres:
        is_selected = atmosphere in selected_atmospheres
        builder.row(
            InlineKeyboardButton(
                text=f"{'✅' if is_selected else '⬜'} {atmosphere}",
                callback_data=f"toggle_atmosphere_{atmosphere}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="✅ Продолжить",
            callback_data="continue_from_atmosphere"
        )
    )
    
    await callback.message.edit_text(
        "Шаг 8/10: Выберите атмосферы (можно несколько)\n\n"
        "Это определит эмоциональный тон рассказа:",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.selecting_atmosphere)
    await callback.answer()

async def finalize_plan_creation(callback: CallbackQuery, state: FSMContext):
    """Финализирует создание плана"""
    
    user_id = callback.from_user.id
    plan_data = plan_drafts[user_id]
    
    # Генерируем итоговый промпт
    final_prompt = build_base_prompt(plan_data)
    
    # Показываем превью плана
    text = f"""📋 *Ваш план готов!*

*Название:* {plan_data['name']}
*Описание:* {plan_data['description']}
*Жанр:* {GENRES[plan_data['genre']]['name']} - {plan_data['subgenre']}
*Аудитория:* {AUDIENCES[plan_data['audience']]}
*Структура:* {STRUCTURES[plan_data['structure']]['name']}
*Объем:* {plan_data['word_count']} слов

*Промпт для AI:*
```
{final_prompt[:1000]}...
```

Сохранить этот план?"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить", callback_data="save_advanced_plan"),
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_advanced_plan")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_advanced_plan")
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    
    await state.set_state(AdvancedPlanStates.reviewing_plan)
    await callback.answer()

# ===== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ =====

def create_plan_from_draft(plan_data: Dict) -> Dict:
    """Создает структуру плана для сохранения в БД"""
    
    final_prompt = build_base_prompt(plan_data)
    
    return {
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
                    "model": "large"  # Используем large для лучшего качества
                }
            },
            {
                "type": "process_with_claude",
                "params": {
                    "prompt": final_prompt,
                    "model": "claude-3-opus-20240229",  # Opus для творческих задач
                    "temperature": 0.8,  # Выше для креативности
                    "max_tokens": 4000
                }
            },
            {
                "type": "generate_speech",
                "params": {
                    "voice": plan_data.get("voice_settings", {}).get("voice", "alena"),
                    "emotion": plan_data.get("voice_settings", {}).get("emotion", "neutral"),
                    "speed": plan_data.get("voice_settings", {}).get("speed", 1.0)
                }
            }
        ],
        "video_steps": [],
        "default_prompt": final_prompt,
        "is_active": True,
        "modules_enabled": ["text"],
        "metadata": {
            "genre": plan_data["genre"],
            "subgenre": plan_data["subgenre"],
            "audience": plan_data["audience"],
            "structure": plan_data["structure"],
            "atmospheres": plan_data["atmospheres"],
            "word_count": plan_data["word_count"]
        }
    }

# ===== ШАБЛОНЫ ГОТОВЫХ ПЛАНОВ =====

PRESET_PLANS = {
    "horror_night": {
        "name": "🌙 Ночные ужасы",
        "description": "Психологические хорроры с нарастающим напряжением",
        "template": """Создай психологический хоррор для аудитории 25-45 лет.

ТРЕБОВАНИЯ:
- Объем: 20000 слов
- Структура: 3 акта с нарастающим напряжением
- Атмосфера: зловещая, тревожная, с элементами паранойи
- Повествование от первого лица для погружения

АКТ 1 (25%): Обычная жизнь героя с тревожными деталями
АКТ 2 (50%): Эскалация странных событий, потеря контроля
АКТ 3 (25%): Кульминация ужаса и шокирующий финал

ВАЖНО: Используй звуковые эффекты в тексте [шорох], [скрип], создавай паузы многоточиями..."""
    },
    
    "detective_classic": {
        "name": "🔍 Классический детектив",
        "description": "Запутанные расследования с неожиданными поворотами",
        "template": """Создай классический детектив в стиле Агаты Кристи.

СТРУКТУРА:
1. Преступление и вызов детектива
2. Сбор улик и опрос свидетелей
3. Ложные следы и подозрения
4. Озарение детектива
5. Драматическое разоблачение

Объем: 20000 слов
Стиль: От третьего лица, всезнающий рассказчик
Включи: детальные описания улик, психологические портреты подозреваемых"""
    }
}

# ===== ИНТЕРФЕЙС ВЫБОРА ШАБЛОНОВ =====

async def show_plan_templates(callback: CallbackQuery):
    """Показывает готовые шаблоны планов"""
    
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="🆕 Создать с нуля",
            callback_data="create_from_scratch"
        )
    )
    
    for template_id, template_info in PRESET_PLANS.items():
        builder.row(
            InlineKeyboardButton(
                text=template_info["name"],
                callback_data=f"use_template_{template_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="📥 Импортировать из файла",
            callback_data="import_plan"
        )
    )
    
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="plans_menu")
    )
    
    await callback.message.edit_text(
        "📚 *Создание плана для рассказов*\n\n"
        "Выберите способ создания:\n\n"
        "• *С нуля* - пошаговый конструктор\n"
        "• *Шаблоны* - готовые проверенные планы\n"
        "• *Импорт* - загрузить из документа",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await callback.answer()