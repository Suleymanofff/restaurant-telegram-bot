from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from fluent.runtime import FluentLocalization

async def get_analytics_keyboard(l10n: FluentLocalization):
    """Клавиатура для аналитики"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="📊 Общая статистика")
    builder.button(text="👥 Анализ пользователей")
    builder.button(text="📈 Активность по дням")
    builder.button(text="🎯 Целевые сегменты")
    builder.button(text="📋 Бронирования")
    builder.button(text="👨‍💼 Вызовы персонала")
    builder.button(text="📋 Брони сегодня")
    builder.button(text="📦 Управление доставкой")
    builder.button(text="🏥 Health Monitor")
    builder.button(text="🔙 В главное меню")
    
    builder.adjust(2, 2, 2, 1, 1, 1)
    return builder.as_markup(resize_keyboard=True)


async def get_settings_keyboard():
    """Клавиатура для настроек (только админы)"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="👑 Управление админами")
    builder.button(text="👨‍💼 Управление официантами") 
    builder.button(text="🍽️ Управление меню")
    builder.button(text="🚫 Блокировка пользователей")
    builder.button(text="🔙 В главное меню")
    
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_admin_management_keyboard():
    """Клавиатура управления админами"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="➕ Добавить админа")
    builder.button(text="➖ Удалить админа")
    builder.button(text="📋 Список админов")
    builder.button(text="🔙 Назад в настройки")
    
    builder.adjust(2, 1, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_staff_management_keyboard():
    """Клавиатура управления официантами"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="➕ Добавить официанта")
    builder.button(text="➖ Удалить официанта")
    builder.button(text="📋 Список официантов")
    builder.button(text="🔙 Назад в настройки")
    
    builder.adjust(2, 1, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_menu_management_keyboard():
    """Клавиатура управления меню"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="🍕 Добавить блюдо")
    builder.button(text="🗑️ Удалить блюдо")
    builder.button(text="📋 Просмотреть меню")
    builder.button(text="🔙 Назад в настройки")
    
    builder.adjust(2, 1, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_block_management_keyboard():
    """Клавиатура блокировки пользователей"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="🚫 Заблокировать")
    builder.button(text="✅ Разблокировать")
    builder.button(text="📋 Заблокированные")
    builder.button(text="🔙 Назад в настройки")
    
    builder.adjust(2, 1, 1)
    return builder.as_markup(resize_keyboard=True)