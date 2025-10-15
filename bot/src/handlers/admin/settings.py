from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from fluent.runtime import FluentLocalization
import logging

from src.states.settings import SettingsStates
from src.database.db_manager import DatabaseManager
from src.utils.config import settings
from src.utils.logger import get_logger
import src.handlers.admin.keyboards as kb

router = Router()
logger = get_logger(__name__)

@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Главное меню настроек (только для админов)"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам.")
        return
    
    keyboard = await kb.get_settings_keyboard()
    await message.answer(
        "⚙️ <b>ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n"
        "Выберите раздел для управления:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "👑 Управление админами")
async def admin_management(message: Message, db_manager: DatabaseManager):
    """Управление администраторами"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return
    
    keyboard = await kb.get_admin_management_keyboard()
    await message.answer(
        "👑 <b>УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ</b>\n\n"
        "Добавление или удаление прав администратора:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "👨‍💼 Управление официантами")
async def staff_management(message: Message, db_manager: DatabaseManager):
    """Управление официантами"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return
    
    keyboard = await kb.get_staff_management_keyboard()
    await message.answer(
        "👨‍💼 <b>УПРАВЛЕНИЕ ОФИЦИАНТАМИ</b>\n\n"
        "Добавление или удаление прав официанта:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "🍽️ Управление меню")
async def menu_management(message: Message, db_manager: DatabaseManager):
    """Управление меню доставки"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return
    
    keyboard = await kb.get_menu_management_keyboard()
    await message.answer(
        "🍽️ <b>УПРАВЛЕНИЕ МЕНЮ ДОСТАВКИ</b>\n\n"
        "Добавление или удаление блюд:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "🚫 Блокировка пользователей")
async def block_management(message: Message, db_manager: DatabaseManager):
    """Управление блокировкой пользователей"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав.")
        return
    
    keyboard = await kb.get_block_management_keyboard()
    await message.answer(
        "🚫 <b>БЛОКИРОВКА ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        "Блокировка и разблокировка пользователей:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "📋 Список админов")
async def list_admins(message: Message, db_manager: DatabaseManager):
    """Показать список администраторов (из базы данных)"""
    try:
        admins = await db_manager.get_admins()
        
        if not admins:
            await message.answer("👑 <b>СПИСОК АДМИНИСТРАТОРОВ</b>\n\nНет администраторов в базе данных.")
            return
        
        text = "👑 <b>СПИСОК АДМИНИСТРАТОРОВ</b>\n\n"
        
        for i, admin in enumerate(admins, 1):
            username = f"@{admin['username']}" if admin.get('username') and admin['username'] != 'unknown' else "нет username"
            created_at = admin.get('created_at', 'неизвестно')
            if hasattr(created_at, 'strftime'):
                created_at = created_at.strftime("%d.%m.%Y %H:%M")
            
            text += f"{i}. {admin['full_name']} ({username})\n"
            text += f"   🆔 ID: {admin['user_id']}\n"
            text += f"   📅 Добавлен: {created_at}\n\n"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Error listing admins: {e}")
        await message.answer("❌ Ошибка при получении списка администраторов")

@router.message(F.text == "📋 Список официантов")
async def list_staff(message: Message, db_manager: DatabaseManager):
    """Показать список официантов (из базы данных)"""
    try:
        staff_list = await db_manager.get_staff()
        
        if not staff_list:
            await message.answer("👨‍💼 <b>СПИСОК ОФИЦИАНТОВ</b>\n\nНет официантов в базе данных.")
            return
        
        text = "👨‍💼 <b>СПИСОК ОФИЦИАНТОВ</b>\n\n"
        
        for i, staff_member in enumerate(staff_list, 1):
            username = f"@{staff_member['username']}" if staff_member.get('username') and staff_member['username'] != 'unknown' else "нет username"
            created_at = staff_member.get('created_at', 'неизвестно')
            if hasattr(created_at, 'strftime'):
                created_at = created_at.strftime("%d.%m.%Y %H:%M")
            
            text += f"{i}. {staff_member['full_name']} ({username})\n"
            text += f"   🆔 ID: {staff_member['user_id']}\n"
            text += f"   📅 Добавлен: {created_at}\n\n"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Error listing staff: {e}")
        await message.answer("❌ Ошибка при получении списка официантов")

@router.message(F.text == "📋 Просмотреть меню")
async def view_menu(message: Message, db_manager: DatabaseManager):
    """Показать текущее меню"""
    try:
        menu_items = await db_manager.get_delivery_menu()
        
        if not menu_items:
            await message.answer("📭 Меню пустое")
            return
        
        text = "🍽️ <b>ТЕКУЩЕЕ МЕНЮ</b>\n\n"
        
        current_category = ""
        for item in menu_items:
            if item['category'] != current_category:
                current_category = item['category']
                category_name = {
                    'breakfasts': '🍳 ЗАВТРАКИ',
                    'hots': '🍲 ГОРЯЧЕЕ', 
                    'hot_drinks': '☕️ ГОРЯЧИЕ НАПИТКИ',
                    'cold_drinks': '🍸 ХОЛОДНЫЕ НАПИТКИ',
                    'deserts': '🍰 ДЕСЕРТЫ'
                }.get(current_category, current_category)
                text += f"\n{category_name}:\n"
            
            status = "✅" if item['is_available'] else "❌"
            text += f"{status} <b>#{item['id']}</b> {item['name']} - {item['price']}₽\n"
            if item.get('description'):
                text += f"   <i>{item['description']}</i>\n"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Error viewing menu: {e}")
        await message.answer("❌ Ошибка при загрузке меню")

@router.message(F.text == "📋 Заблокированные")
async def list_blocked_users(message: Message, db_manager: DatabaseManager):
    """Показать заблокированных пользователей"""
    try:
        blocked_users = await db_manager.get_blocked_users()
        
        if not blocked_users:
            await message.answer("✅ Нет заблокированных пользователей")
            return
        
        text = "🚫 <b>ЗАБЛОКИРОВАННЫЕ ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        
        for i, user in enumerate(blocked_users, 1):
            username = f"@{user['username']}" if user.get('username') else "нет username"
            text += f"{i}. {user['full_name']} ({username}) - ID: {user['user_id']}\n"
            
            # Форматируем дату блокировки
            blocked_at = user.get('updated_at', 'неизвестно')
            if hasattr(blocked_at, 'strftime'):
                blocked_at = blocked_at.strftime("%d.%m.%Y %H:%M")
            text += f"   📅 Заблокирован: {blocked_at}\n\n"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Error listing blocked users: {e}")
        await message.answer("❌ Ошибка при получении списка заблокированных")

@router.message(F.text == "🔙 Назад в настройки")
async def back_to_settings(message: Message, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Возврат в главное меню настроек"""
    await settings_menu(message, l10n, db_manager)

@router.message(F.text == "🔙 В главное меню")
async def back_to_main_menu_from_settings(message: Message, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Возврат в главное меню из настроек"""
    from src.handlers.user.message import show_main_menu
    await show_main_menu(message, l10n, db_manager)