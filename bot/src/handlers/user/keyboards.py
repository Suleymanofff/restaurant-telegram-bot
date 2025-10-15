from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from fluent.runtime import FluentLocalization
from src.utils.config import settings
import logging

logger = logging.getLogger(__name__)

async def get_sex_of_user_kb(l10n: FluentLocalization):
    """Инлайн клавиатура для получения пола пользователя"""
    kb = InlineKeyboardBuilder()
    kb.button(
        text=l10n.format_value("male-user"),
        callback_data="user_sex_male"
    )
    kb.button(
        text=l10n.format_value("female-user"),
        callback_data="user_sex_female"
    )
    kb.adjust(1)

    return kb.as_markup()

async def get_user_major_kb(l10n: FluentLocalization):
    """Инлайн клавиатура для получения профессии пользователя"""
    kb = InlineKeyboardBuilder()
    kb.button(
        text=l10n.format_value("major-student"),
        callback_data="user_major_student"
    )
    kb.button(
        text=l10n.format_value("major-entrepreneur"),
        callback_data="user_major_entrepreneur"
    )
    kb.button(
        text=l10n.format_value("major-hire"),
        callback_data="user_major_hire"
    )
    kb.button(
        text=l10n.format_value("major-frilans"),
        callback_data="user_major_frilans"
    )
    kb.adjust(1)

    return kb.as_markup()

async def get_main_menu_keyboard(l10n: FluentLocalization, user_id: int, db_manager=None):
    """Главное меню с кнопками (с проверкой прав через базу данных)"""
    builder = ReplyKeyboardBuilder()
    
    # Проверяем права пользователя через базу данных
    is_admin = False
    is_staff = False
    
    if db_manager:
        try:
            is_admin = await db_manager.is_admin(user_id)
            is_staff = await db_manager.is_staff(user_id)
        except Exception as e:
            # Fallback: если база недоступна, используем статическую проверку
            from src.utils.config import settings
            is_admin = await settings.is_admin(user_id)
            is_staff = await settings.is_staff(user_id)
            logger.error(f"❌ Database error in menu keyboard: {e}")
    else:
        # Fallback: если db_manager не передан
        from src.utils.config import settings
        is_admin = await settings.is_admin(user_id)
        is_staff = await settings.is_staff(user_id)
    
    # Первый ряд - для всех пользователей
    builder.button(text=l10n.format_value("menu-btn"))

    # Второй ряд - для всех пользователей
    builder.button(text=l10n.format_value("call-staff-btn"))
    builder.button(text=l10n.format_value("make-reservation-btn"))
    
    # Третий ряд - для всех пользователей
    builder.button(text=l10n.format_value("delivery-btn"))
    
    # Четвертый ряд - для всех пользователей
    builder.button(text=l10n.format_value("invite-friend-btn"))
    builder.button(text=l10n.format_value("loyalty-program-btn"))
    
    # Пятый ряд - для всех пользователей
    builder.button(text=l10n.format_value("get-directions-btn"))
    
    # Шестой ряд - ТОЛЬКО ДЛЯ АДМИНИСТРАТОРОВ
    if is_admin:
        builder.button(text=l10n.format_value("broadcast-btn"))
        builder.button(text=l10n.format_value("analytics-btn"))
        builder.button(text=l10n.format_value("settings-btn"))
    
    # Настройка расположения кнопок в зависимости от прав
    if is_admin:
        # Администратор видит все кнопки
        builder.adjust(1, 2, 1, 2, 1, 1, 2)
    elif is_staff:
        # Официант видит основные кнопки + кнопки персонала
        builder.adjust(1, 2, 1, 2, 1, 1)
    else:
        # Обычный пользователь видит только основные кнопки
        builder.adjust(1, 2, 1, 2, 1, 1)
        
    return builder.as_markup(resize_keyboard=True)

async def confirm_staff_message(l10n: FluentLocalization):
    # Клавиатура с подтверждением
    builder = InlineKeyboardBuilder()
    builder.button(
        text=l10n.format_value("confirm-btn"), 
        callback_data="confirm_staff_call"
    )
    builder.button(
        text=l10n.format_value("cancel-btn"), 
        callback_data="cancel_staff_call"
    )
    builder.adjust(2)
    return builder.as_markup()

async def menu_food_types(l10n: FluentLocalization):
    """Клавиатура с типами блюд"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text=l10n.format_value("menu-breakfasts"))
    builder.button(text=l10n.format_value("menu-hot-foods"))
    builder.button(text=l10n.format_value("menu-hot-drinks"))
    builder.button(text=l10n.format_value("menu-cold-drinks"))
    builder.button(text=l10n.format_value("menu-deserts"))
    builder.button(text=l10n.format_value("menu-go-back"))

    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

# 🔥 НОВЫЕ КЛАВИАТУРЫ ДЛЯ ДОСТАВКИ

async def get_delivery_categories_kb(l10n: FluentLocalization):
    """Клавиатура категорий доставки"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="🍳 ЗАВТРАКИ")
    builder.button(text="🍲 ГОРЯЧЕЕ")
    builder.button(text="☕️ ГОРЯЧИЕ НАПИТКИ")
    builder.button(text="🍸 ХОЛОДНЫЕ НАПИТКИ")
    builder.button(text="🍰 ДЕСЕРТЫ")
    builder.button(text="🛒 Корзина")
    builder.button(text="🔙 Назад")
    
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup(resize_keyboard=True)

async def get_delivery_menu_kb(l10n: FluentLocalization):
    """Клавиатура действий в меню доставки"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="🛒 Корзина")
    builder.button(text="📋 Категории")
    builder.button(text="🔙 Назад")
    
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_cart_kb(l10n: FluentLocalization):
    """Клавиатура для корзины"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="✅ Оформить заказ")
    builder.button(text="🗑️ Очистить корзину")
    builder.button(text="📋 Продолжить покупки")
    builder.button(text="🔙 Назад")
    
    builder.adjust(1, 2, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_delivery_time_kb(l10n: FluentLocalization):
    """Клавиатура выбора времени доставки"""
    builder = ReplyKeyboardBuilder()
    
    # Ближайшие временные слоты
    builder.button(text="Как можно скорее")
    builder.button(text="Через 1 час")
    builder.button(text="Через 2 часа")
    builder.button(text="Уточню позже")
    builder.button(text="🔙 Назад")
    
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup(resize_keyboard=True)

async def get_confirmation_kb(l10n: FluentLocalization):
    """Клавиатура подтверждения заказа"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(text="✅ Подтвердить заказ")
    builder.button(text="❌ Отменить")
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

async def get_back_kb(l10n: FluentLocalization):
    """Простая клавиатура с кнопкой Назад"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔙 Назад")
    return builder.as_markup(resize_keyboard=True)


async def get_phone_keyboard(l10n: FluentLocalization):
    """Клавиатура для запроса телефона"""
    builder = ReplyKeyboardBuilder()
    
    # Кнопка для отправки телефона
    builder.button(
        text="📞 Поделиться телефоном", 
        request_contact=True
    )
    builder.button(text="🔙 Назад")
    
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True  # Скрыть клавиатуру после использования
    )

async def get_phone_keyboard_with_cancel(l10n: FluentLocalization):
    """Клавиатура для запроса телефона с отменой"""
    builder = ReplyKeyboardBuilder()
    
    # Кнопка для отправки телефона
    builder.button(
        text="📞 Поделиться телефоном", 
        request_contact=True
    )
    builder.button(text="❌ Отмена")
    
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True
    )

async def get_phone_input_kb(l10n: FluentLocalization):
    """Клавиатура для ввода телефона в доставке"""
    builder = ReplyKeyboardBuilder()
    
    builder.button(
        text="📞 Поделиться телефоном", 
        request_contact=True
    )
    builder.button(text="🔙 Назад")
    
    builder.adjust(1)
    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True
    )