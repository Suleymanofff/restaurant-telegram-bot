from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluent.runtime import FluentLocalization
import logging

from src.states.settings import SettingsStates
from src.database.db_manager import DatabaseManager
from src.utils.config import settings
import src.handlers.admin.keyboards as kb

router = Router()
logger = logging.getLogger(__name__)

# ==================== INLINE KEYBOARDS ====================

def get_cancel_keyboard():
    """Создает инлайн клавиатуру с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_operation")
    return builder.as_markup()

# ==================== CANCEL HANDLER ====================

@router.callback_query(F.data == "cancel_operation")
async def cancel_operation(callback: CallbackQuery, state: FSMContext):
    """Обработка отмены операции - возврат к предыдущему меню"""
    await state.clear()
    
    # Определяем, из какого меню пришли, и возвращаемся туда
    current_state = await state.get_state()
    
    if current_state in [
        SettingsStates.waiting_for_admin_id,
        SettingsStates.waiting_for_remove_admin_id
    ]:
        # Возврат в меню управления админами
        await callback.message.edit_text(
            "👑 <b>УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ</b>\n\n"
            "Добавление или удаление прав администратора:",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await kb.get_admin_management_keyboard()
        )
    
    elif current_state in [
        SettingsStates.waiting_for_staff_id,
        SettingsStates.waiting_for_remove_staff_id
    ]:
        # Возврат в меню управления официантами
        await callback.message.edit_text(
            "👨‍💼 <b>УПРАВЛЕНИЕ ОФИЦИАНТАМИ</b>\n\n"
            "Добавление или удаление прав официанта:",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await kb.get_staff_management_keyboard()
        )
    
    elif current_state in [
        SettingsStates.waiting_for_menu_category,
        SettingsStates.waiting_for_dish_name,
        SettingsStates.waiting_for_dish_description,
        SettingsStates.waiting_for_dish_price,
        SettingsStates.waiting_for_remove_dish_id
    ]:
        # Возврат в меню управления меню
        await callback.message.edit_text(
            "🍽️ <b>УПРАВЛЕНИЕ МЕНЮ ДОСТАВКИ</b>\n\n"
            "Добавление или удаление блюд:",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await kb.get_menu_management_keyboard()
        )
    
    elif current_state in [
        SettingsStates.waiting_for_block_user_id,
        SettingsStates.waiting_for_unblock_user_id
    ]:
        # Возврат в меню блокировки пользователей
        await callback.message.edit_text(
            "🚫 <b>БЛОКИРОВКА ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
            "Блокировка и разблокировка пользователей:",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await kb.get_block_management_keyboard()
        )
    
    else:
        # Возврат в главное меню настроек
        await callback.message.edit_text(
            "⚙️ <b>ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n"
            "Выберите раздел для управления:",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await kb.get_settings_keyboard()
        )
    
    await callback.answer("❌ Операция отменена")

# ==================== ADMIN MANAGEMENT ====================

@router.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало добавления администратора"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    await message.answer(
        "👑 <b>Добавление администратора</b>\n\n"
        "Введите ID пользователя, которого хотите сделать администратором:\n"
        "💡 <i>ID можно получить с помощью бота @userinfobot</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_admin_id)

@router.message(SettingsStates.waiting_for_admin_id, F.text)
async def add_admin_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение добавления администратора"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Проверяем, не является ли пользователь уже админом
    if await db_manager.is_admin(user_id):
        await message.answer(
            "❌ Этот пользователь уже является администратором.",
            reply_markup=await kb.get_admin_management_keyboard()
        )
        await state.clear()
        return

    # Получаем информацию о пользователе (если есть в базе)
    user = await db_manager.get_user(user_id)
    username = user.get('username', 'unknown') if user else 'unknown'
    full_name = user.get('full_name', f'User_{user_id}') if user else f'User_{user_id}'

    success = await db_manager.add_admin(user_id, username, full_name)
    if success:
        await message.answer(
            f"✅ Пользователь {full_name} (ID: {user_id}) добавлен в администраторы.",
            reply_markup=await kb.get_admin_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось добавить пользователя {user_id} в администраторы.",
            reply_markup=await kb.get_admin_management_keyboard()
        )
    await state.clear()

@router.message(F.text == "➖ Удалить админа")
async def remove_admin_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало удаления администратора"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    # Показываем список админов для удобства
    admins = await db_manager.get_admins()
    if not admins:
        await message.answer("❌ Нет администраторов для удаления.")
        return

    text = "👑 <b>Текущие администраторы:</b>\n\n"
    for admin in admins:
        text += f"• ID: {admin['user_id']} - {admin['full_name']} (@{admin['username']})\n"

    text += "\nВведите ID администратора, которого хотите удалить:"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_remove_admin_id)

@router.message(SettingsStates.waiting_for_remove_admin_id, F.text)
async def remove_admin_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение удаления администратора"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Не позволяем удалить себя
    if user_id == message.from_user.id:
        await message.answer("❌ Вы не можете удалить сами себя.")
        await state.clear()
        return

    success = await db_manager.remove_admin(user_id)
    if success:
        await message.answer(
            f"✅ Пользователь {user_id} удален из администраторов.",
            reply_markup=await kb.get_admin_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось удалить пользователя {user_id} из администраторов.",
            reply_markup=await kb.get_admin_management_keyboard()
        )
    await state.clear()

# ==================== STAFF MANAGEMENT ====================

@router.message(F.text == "➕ Добавить официанта")
async def add_staff_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало добавления официанта"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    await message.answer(
        "👨‍💼 <b>Добавление официанта</b>\n\n"
        "Введите ID пользователя, которого хотите сделать официантом:\n"
        "💡 <i>ID можно получить с помощью бота @userinfobot</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_staff_id)

@router.message(SettingsStates.waiting_for_staff_id, F.text)
async def add_staff_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение добавления официанта"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Проверяем, не является ли пользователь уже официантом
    if await db_manager.is_staff(user_id):
        await message.answer(
            "❌ Этот пользователь уже является официантом.",
            reply_markup=await kb.get_staff_management_keyboard()
        )
        await state.clear()
        return

    # Получаем информацию о пользователе
    user = await db_manager.get_user(user_id)
    username = user.get('username', 'unknown') if user else 'unknown'
    full_name = user.get('full_name', f'User_{user_id}') if user else f'User_{user_id}'

    success = await db_manager.add_staff(user_id, username, full_name)
    if success:
        await message.answer(
            f"✅ Пользователь {full_name} (ID: {user_id}) добавлен в официанты.",
            reply_markup=await kb.get_staff_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось добавить пользователя {user_id} в официанты.",
            reply_markup=await kb.get_staff_management_keyboard()
        )
    await state.clear()

@router.message(F.text == "➖ Удалить официанта")
async def remove_staff_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало удаления официанта"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    # Показываем список официантов для удобства
    staff = await db_manager.get_staff()
    if not staff:
        await message.answer("❌ Нет официантов для удаления.")
        return

    text = "👨‍💼 <b>Текущие официанты:</b>\n\n"
    for staff_member in staff:
        text += f"• ID: {staff_member['user_id']} - {staff_member['full_name']} (@{staff_member['username']})\n"

    text += "\nВведите ID официанта, которого хотите удалить:"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_remove_staff_id)

@router.message(SettingsStates.waiting_for_remove_staff_id, F.text)
async def remove_staff_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение удаления официанта"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    success = await db_manager.remove_staff(user_id)
    if success:
        await message.answer(
            f"✅ Пользователь {user_id} удален из официантов.",
            reply_markup=await kb.get_staff_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось удалить пользователя {user_id} из официантов.",
            reply_markup=await kb.get_staff_management_keyboard()
        )
    await state.clear()

# ==================== MENU MANAGEMENT ====================

@router.message(F.text == "🍕 Добавить блюдо")
async def add_dish_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало добавления блюда"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    categories = await db_manager.get_delivery_categories()
    if not categories:
        await message.answer("❌ Нет категорий для добавления блюда.")
        return

    text = "🍽️ <b>Добавление блюда</b>\n\n"
    text += "Выберите категорию:\n"
    for category in categories:
        category_name = {
            'breakfasts': '🍳 ЗАВТРАКИ',
            'hots': '🍲 ГОРЯЧЕЕ', 
            'hot_drinks': '☕️ ГОРЯЧИЕ НАПИТКИ',
            'cold_drinks': '🍸 ХОЛОДНЫЕ НАПИТКИ',
            'deserts': '🍰 ДЕСЕРТЫ'
        }.get(category['category'], category['category'])
        text += f"• {category_name}\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_menu_category)

@router.message(SettingsStates.waiting_for_menu_category, F.text)
async def add_dish_category(message: Message, state: FSMContext):
    """Обработка выбора категории для блюда"""
    category_map = {
        'breakfasts': '🍳 ЗАВТРАКИ',
        'hots': '🍲 ГОРЯЧЕЕ', 
        'hot_drinks': '☕️ ГОРЯЧИЕ НАПИТКИ',
        'cold_drinks': '🍸 ХОЛОДНЫЕ НАПИТКИ',
        'deserts': '🍰 ДЕСЕРТЫ'
    }
    
    # Ищем категорию по русскому названию или английскому
    category_input = message.text.strip()
    category = category_map.get(category_input, category_input.lower())
    
    await state.update_data(category=category)
    
    await message.answer(
        "Введите название блюда:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_dish_name)

@router.message(SettingsStates.waiting_for_dish_name, F.text)
async def add_dish_name(message: Message, state: FSMContext):
    """Обработка названия блюда"""
    name = message.text.strip()
    await state.update_data(name=name)
    
    await message.answer(
        "Введите описание блюда (или отправьте '-' чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_dish_description)

@router.message(SettingsStates.waiting_for_dish_description, F.text)
async def add_dish_description(message: Message, state: FSMContext):
    """Обработка описания блюда"""
    description = message.text.strip()
    if description == '-':
        description = None
    await state.update_data(description=description)
    
    await message.answer(
        "Введите цену блюда (в рублях, только число):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_dish_price)

@router.message(SettingsStates.waiting_for_dish_price, F.text)
async def add_dish_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение добавления блюда"""
    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат цены. Введите число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    data = await state.get_data()
    category = data['category']
    name = data['name']
    description = data.get('description')

    # Добавляем блюдо в базу
    success = await db_manager.add_dish_to_menu(category, name, description, price)
    if success:
        await message.answer(
            f"✅ Блюдо '{name}' успешно добавлено в категорию '{category}'.",
            reply_markup=await kb.get_menu_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось добавить блюдо '{name}'.",
            reply_markup=await kb.get_menu_management_keyboard()
        )
    await state.clear()

@router.message(F.text == "🗑️ Удалить блюдо")
async def remove_dish_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало удаления блюда"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    menu_items = await db_manager.get_delivery_menu()
    if not menu_items:
        await message.answer("❌ Меню пустое.")
        return

    text = "🍽️ <b>Текущее меню:</b>\n\n"
    for item in menu_items:
        text += f"• ID: {item['id']} - {item['name']} ({item['price']}₽)\n"

    text += "\nВведите ID блюда, которое хотите удалить:"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_remove_dish_id)

@router.message(SettingsStates.waiting_for_remove_dish_id, F.text)
async def remove_dish_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение удаления блюда"""
    try:
        dish_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    success = await db_manager.remove_dish_from_menu(dish_id)
    if success:
        await message.answer(
            f"✅ Блюдо с ID {dish_id} удалено.",
            reply_markup=await kb.get_menu_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось удалить блюдо с ID {dish_id}.",
            reply_markup=await kb.get_menu_management_keyboard()
        )
    await state.clear()

# ==================== BLOCK MANAGEMENT ====================

@router.message(F.text == "🚫 Заблокировать")
async def block_user_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало блокировки пользователя"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    await message.answer(
        "🚫 <b>Блокировка пользователя</b>\n\n"
        "Введите ID пользователя, которого хотите заблокировать:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_block_user_id)

@router.message(SettingsStates.waiting_for_block_user_id, F.text)
async def block_user_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение блокировки пользователя"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    # Не позволяем заблокировать себя
    if user_id == message.from_user.id:
        await message.answer("❌ Вы не можете заблокировать сами себя.")
        await state.clear()
        return

    success = await db_manager.block_user(user_id)
    if success:
        await message.answer(
            f"✅ Пользователь {user_id} заблокирован.",
            reply_markup=await kb.get_block_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось заблокировать пользователя {user_id}.",
            reply_markup=await kb.get_block_management_keyboard()
        )
    await state.clear()

@router.message(F.text == "✅ Разблокировать")
async def unblock_user_start(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Начало разблокировки пользователя"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return

    await message.answer(
        "✅ <b>Разблокировка пользователя</b>\n\n"
        "Введите ID пользователя, которого хотите разблокировать:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()  # Кнопка отмены в том же сообщении
    )
    await state.set_state(SettingsStates.waiting_for_unblock_user_id)

@router.message(SettingsStates.waiting_for_unblock_user_id, F.text)
async def unblock_user_finish(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Завершение разблокировки пользователя"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID. Введите целое число.",
            reply_markup=get_cancel_keyboard()
        )
        return

    success = await db_manager.unblock_user(user_id)
    if success:
        await message.answer(
            f"✅ Пользователь {user_id} разблокирован.",
            reply_markup=await kb.get_block_management_keyboard()
        )
    else:
        await message.answer(
            f"❌ Не удалось разблокировать пользователя {user_id}.",
            reply_markup=await kb.get_block_management_keyboard()
        )
    await state.clear()