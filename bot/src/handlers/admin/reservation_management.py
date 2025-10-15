from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.database.db_manager import DatabaseManager
from src.utils.config import settings
from fluent.runtime import FluentLocalization
from src.handlers.user.reservation import notify_user_about_reservation_status
from datetime import date, datetime, time
from src.utils.time_utils import format_restaurant_time, parse_reservation_datetime
from src.utils.logger import get_logger

router = Router()
logger = get_logger(__name__)

@router.message(Command("reservations"))
@router.message(F.text == "📋 Управление бронями")
async def show_reservations_menu(message: Message, db_manager: DatabaseManager, l10n: FluentLocalization):
    """Показ меню управления бронями"""
    # Проверяем через базу данных
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("У вас нет прав для управления бронями.")
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏳ Ожидающие", callback_data="admin_pending_reservations"),
        InlineKeyboardButton(text="✅ Подтвержденные", callback_data="admin_confirmed_reservations")
    )
    builder.row(
        InlineKeyboardButton(text="📅 Сегодня", callback_data="admin_today_reservations"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_reservations_stats")
    )
    
    await message.answer(
        "📋 Меню управления бронями:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_pending_reservations")
async def show_pending_reservations(callback: CallbackQuery, db_manager: DatabaseManager, l10n: FluentLocalization):
    """Показ ожидающих подтверждения броней"""
    reservations = await db_manager.get_reservations_by_status("pending")
    
    if not reservations:
        await callback.message.edit_text("⏳ Нет ожидающих подтверждения броней.")
        return
    
    for reservation in reservations[:5]:  # Показываем первые 5
        reservation_text = format_reservation_text(reservation, "ОЖИДАЕТ - ")
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm_{reservation['id']}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{reservation['id']}")
        )
        
        await callback.message.answer(reservation_text, reply_markup=builder.as_markup())
    
    await callback.answer()

@router.callback_query(F.data.startswith("admin_confirm_"))
async def confirm_reservation_admin(callback: CallbackQuery, db_manager: DatabaseManager, l10n: FluentLocalization, bot: Bot):
    """Подтверждение брони администратором - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    try:
        reservation_id = int(callback.data.split("_")[2])
        logger.info(f"🔄 Admin confirming reservation #{reservation_id}")
        
        success = await db_manager.update_reservation_status(reservation_id, "confirmed")
        
        if success:
            # Получаем обновленные данные брони
            reservation = await db_manager.get_reservation_by_id(reservation_id)
            if reservation:
                # Уведомляем пользователя - ПЕРЕДАЕМ ОБЪЕКТЫ, А НЕ СТРОКИ
                await notify_user_about_reservation_status(
                    bot, reservation['user_id'], 
                    {
                        'id': reservation_id,
                        'date': reservation['reservation_date'],  # объект date
                        'time': reservation['reservation_time'],  # объект time
                        'guests': reservation['guests_count'],
                        'name': reservation['customer_name'],
                        'phone': reservation['customer_phone'],
                        'status': 'подтверждена'
                    },
                    l10n
                )
                
                # Обновляем сообщение у администратора с полной информацией
                updated_text = format_reservation_text(reservation, "ПОДТВЕРЖДЕНА - ")
                
                await callback.message.edit_text(
                    updated_text,
                    reply_markup=None
                )
                logger.info(f"✅ Reservation #{reservation_id} confirmed by admin")
            else:
                await callback.message.edit_text("❌ Бронь не найдена после подтверждения")
        else:
            await callback.message.edit_text("❌ Ошибка при подтверждении брони")
            logger.error(f"❌ Failed to confirm reservation #{reservation_id}")
        
    except Exception as e:
        logger.error(f"❌ Error in confirm_reservation_admin: {e}")
        await callback.message.edit_text("❌ Ошибка при подтверждении брони")
    
    await callback.answer()

@router.callback_query(F.data.startswith("admin_reject_"))
async def reject_reservation_admin(callback: CallbackQuery, db_manager: DatabaseManager, l10n: FluentLocalization, bot: Bot):
    """Отклонение брони администратором"""
    try:
        reservation_id = int(callback.data.split("_")[2])
        print(f"🔄 Admin rejecting reservation #{reservation_id}")
        
        success = await db_manager.update_reservation_status(reservation_id, "cancelled")
        
        if success:
            # Получаем обновленные данные брони
            reservation = await db_manager.get_reservation_by_id(reservation_id)
            if reservation:
                # Уведомляем пользователя
                await notify_user_about_reservation_status(
                    bot, reservation['user_id'], 
                    {
                        'id': reservation_id,
                        'date': str(reservation['reservation_date']),
                        'time': str(reservation['reservation_time']),
                        'guests': reservation['guests_count'],
                        'name': str(reservation['customer_name']),
                        'phone': str(reservation['customer_phone']),
                        'status': 'отклонена'
                    },
                    l10n
                )
                
                # Обновляем сообщение у администратора с полной информацией
                updated_text = format_reservation_text(reservation, "ОТКЛОНЕНА - ")
                
                await callback.message.edit_text(
                    updated_text,
                    reply_markup=None  # Убираем кнопки после отклонения
                )
                print(f"✅ Reservation #{reservation_id} rejected by admin")
            else:
                await callback.message.edit_text("❌ Бронь не найдена после отклонения")
        else:
            await callback.message.edit_text("❌ Ошибка при отклонении брони")
            print(f"❌ Failed to reject reservation #{reservation_id}")
        
    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при отклонении брони")
        print(f"❌ Error in reject_reservation_admin: {e}")
    
    await callback.answer()


def format_reservation_text(reservation: dict, status_prefix: str = "") -> str:
    """Форматирует текст брони для отображения администраторам с правильным временем"""
    
    try:
        # Используем универсальную функцию для парсинга даты и времени
        reservation_datetime = parse_reservation_datetime(
            reservation['reservation_date'],
            reservation['reservation_time']
        )
        
        if reservation_datetime:
            formatted_time = format_restaurant_time(reservation_datetime)
            # Форматируем дату
            if isinstance(reservation['reservation_date'], (datetime, date)):
                formatted_date = reservation['reservation_date'].strftime("%d.%m.%Y")
            else:
                try:
                    if '-' in str(reservation['reservation_date']):
                        year, month, day = map(int, str(reservation['reservation_date']).split('-'))
                        formatted_date = f"{day:02d}.{month:02d}.{year}"
                    else:
                        formatted_date = str(reservation['reservation_date'])
                except:
                    formatted_date = str(reservation['reservation_date'])
        else:
            # Fallback
            formatted_time = str(reservation['reservation_time'])
            formatted_date = str(reservation['reservation_date'])
        
        # Форматируем время создания брони
        created_at = reservation['created_at']
        formatted_created_at = format_restaurant_time(created_at)
        
    except Exception as e:
        logger.error(f"❌ Error formatting reservation text: {e}")
        # Fallback значения
        formatted_date = str(reservation.get('reservation_date', 'N/A'))
        formatted_time = str(reservation.get('reservation_time', 'N/A'))
        formatted_created_at = str(reservation.get('created_at', 'N/A'))
    
    status_emoji = {
        'confirmed': '✅',
        'cancelled': '❌',
        'pending': '⏳',
        'completed': '🎉'
    }.get(reservation.get('status', 'pending'), '📋')
    
    base_text = f"""
{status_emoji} {status_prefix}Бронь #{reservation['id']}

📅 Дата: {formatted_date}
🕐 Время: {formatted_time}
👥 Гости: {reservation['guests_count']}
👤 Имя: {reservation['customer_name']}
📞 Телефон: {reservation['customer_phone']}
👤 ID пользователя: {reservation['user_id']}

📊 Статус: {reservation.get('status', 'pending')}
⏰ Создана: {formatted_created_at}
"""
    
    if reservation.get('notes'):
        base_text += f"📝 Заметки: {reservation['notes']}\n"
    
    return base_text