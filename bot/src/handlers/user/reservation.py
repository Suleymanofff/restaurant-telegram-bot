from datetime import date, datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, Contact
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.handlers.user.message import show_main_menu
from src.states.reservation import ReservationStates
from src.keyboards.calendar import Calendar
from src.utils.config import settings
from src.database.db_manager import DatabaseManager
from fluent.runtime import FluentLocalization
from src.utils.logger import get_logger
from src.utils.rate_limiter import rate_limit, reservation_limit
import src.handlers.user.keyboards as kb
from src.utils.time_utils import format_restaurant_time, parse_reservation_datetime

router = Router()
logger = get_logger(__name__)

# Создаем клавиатуру для отмены
def get_cancel_keyboard(l10n: FluentLocalization):
    """Клавиатура с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reservation")
    )
    return builder.as_markup()

# Создаем клавиатуру для выбора количества гостей
def get_guests_keyboard():
    """Клавиатура с цифрами от 1 до 20 для выбора количества гостей"""
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки с цифрами от 1 до 20
    for i in range(1, 21):
        builder.add(InlineKeyboardButton(text=str(i), callback_data=f"guests_{i}"))
    
    # Располагаем кнопки в 5 рядов по 4 кнопки
    builder.adjust(4, 4, 4, 4, 4)
    
    # Добавляем кнопку отмены
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reservation"))
    
    return builder.as_markup()

async def notify_admins_about_reservation(bot, reservation_data: dict, l10n: FluentLocalization):
    """Уведомление администраторов о новой брони с правильным временем"""
    from src.utils.config import settings
    
    admin_ids = [int(admin_id.strip()) for admin_id in settings.ADMIN_IDS.split(",")]
    
    user_info = f"{reservation_data['user_full_name']}"
    if reservation_data.get('username'):
        user_info += f" (@{reservation_data['username']})"
    
    try:
        # Используем универсальную функцию парсинга
        reservation_datetime = parse_reservation_datetime(
            reservation_data['date'],
            reservation_data['time']
        )
        
        if reservation_datetime:
            formatted_time = format_restaurant_time(reservation_datetime)
            # Форматируем дату
            if isinstance(reservation_data['date'], (datetime, date)):
                formatted_date = reservation_data['date'].strftime("%d.%m.%Y")
            else:
                try:
                    if '-' in str(reservation_data['date']):
                        year, month, day = map(int, str(reservation_data['date']).split('-'))
                        formatted_date = f"{day:02d}.{month:02d}.{year}"
                    else:
                        formatted_date = str(reservation_data['date'])
                except:
                    formatted_date = str(reservation_data['date'])
        else:
            formatted_time = reservation_data['time']
            formatted_date = reservation_data['date']
            
    except Exception as e:
        logger.error(f"❌ Error formatting time in admin notification: {e}")
        formatted_time = reservation_data['time']
        formatted_date = reservation_data['date']
    
    message_text = f"""
🆕 <b>Новая бронь #{reservation_data['id']}</b>

📅 <b>Дата:</b> {formatted_date}
🕐 <b>Время:</b> {formatted_time}
👥 <b>Гости:</b> {reservation_data['guests']}
👤 <b>Имя:</b> {reservation_data['name']}
📞 <b>Телефон:</b> {reservation_data['phone']}
👤 <b>Пользователь:</b> {user_info}
🆔 <b>ID пользователя:</b> {reservation_data['user_id']}
    """
    
    # Создаем клавиатуру с кнопками управления
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить", 
            callback_data=f"admin_confirm_{reservation_data['id']}"
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", 
            callback_data=f"admin_reject_{reservation_data['id']}"
        )
    )
    
    keyboard = builder.as_markup()
    
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, message_text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"✅ Sent reservation notification to admin {admin_id} with correct timezone")
        except Exception as e:
            logger.error(f"❌ Failed to send notification to admin {admin_id}: {e}")

async def notify_user_about_reservation_status(bot, user_id: int, reservation_data: dict, l10n: FluentLocalization):
    """Уведомление пользователя о статусе брони с правильным временем"""
    
    try:
        # Используем универсальную функцию парсинга
        reservation_datetime = parse_reservation_datetime(
            reservation_data['date'], 
            reservation_data['time']
        )
        
        if reservation_datetime:
            formatted_time = format_restaurant_time(reservation_datetime)
            # Форматируем дату в привычный формат
            if isinstance(reservation_data['date'], (datetime, date)):
                formatted_date = reservation_data['date'].strftime("%d.%m.%Y")
            else:
                # Если дата в строковом формате, пытаемся преобразовать
                try:
                    if '-' in str(reservation_data['date']):
                        # Формат "2025-10-10" -> "10.10.2025"
                        year, month, day = map(int, str(reservation_data['date']).split('-'))
                        formatted_date = f"{day:02d}.{month:02d}.{year}"
                    else:
                        formatted_date = str(reservation_data['date'])
                except:
                    formatted_date = str(reservation_data['date'])
        else:
            # Fallback на оригинальные значения
            formatted_time = str(reservation_data['time'])
            formatted_date = str(reservation_data['date'])
        
        status = reservation_data['status']
        
        # Создаем правильное сообщение с отформатированным временем
        message_text = f"""
📋 Статус вашей брони #{reservation_data['id']}

📅 Дата: {formatted_date}
🕐 Время: {formatted_time}
👥 Гости: {reservation_data['guests']}
👤 Имя: {reservation_data['name']}
📞 Телефон: {reservation_data['phone']}

🗒️ Статус: {f"✅ {status}" if status == "подтверждена" else f"❌ {status}"}
        """
        
        await bot.send_message(user_id, message_text)
        logger.info(f"✅ Sent status notification to user {user_id} with correct timezone")
        
    except Exception as e:
        logger.error(f"❌ Error in notify_user_about_reservation_status: {e}")
        # Fallback сообщение
        fallback_text = f"""
📋 Статус вашей брони #{reservation_data['id']}

Статус: {f"✅ {reservation_data['status']}" if reservation_data['status'] == "подтверждена" else f"❌ {reservation_data['status']}"}

Мы свяжемся с вами для уточнения деталей.
        """
        await bot.send_message(user_id, fallback_text)

async def show_reservation_summary(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Показ сводки бронирования для подтверждения"""
    data = await state.get_data()
    
    summary_text = f"""
📋 Подтвердите данные бронирования:

📅 Дата: {data['selected_date']}
🕐 Время: {data['selected_time']}
👥 Гости: {data['guests_count']}
👤 Имя: {data['customer_name']}
📞 Телефон: {data['customer_phone']}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_reservation"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reservation")
    )
    
    await message.answer(summary_text, reply_markup=builder.as_markup())
    await state.set_state(ReservationStates.confirmation)

@router.message(F.text == "🍽️ Забронировать стол")
@router.message(Command("reserve"))
@reservation_limit(cooldown=30)
async def start_reservation(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Начало процесса бронирования"""
    await state.set_state(ReservationStates.waiting_for_date)
    await message.answer(
        "📅 Выберите дату бронирования:",
        reply_markup=Calendar.get_calendar_keyboard()
    )

@router.callback_query(F.data.startswith("calendar_"), ReservationStates.waiting_for_date)
async def process_calendar(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization):
    """Обработка взаимодействия с календарем"""
    action = callback.data.split("_")[1]
    
    if action == "select":
        # Пользователь выбрал дату
        _, _, year, month, day = callback.data.split("_")
        # Убираем ведущие нули если есть
        day = str(int(day))
        month = str(int(month))
        selected_date = f"{day}.{month}.{year}"
        
        await state.update_data(selected_date=selected_date)
        await state.set_state(ReservationStates.waiting_for_time)
        
        await callback.message.edit_text(
            f"🕐 Выберите время бронирования на {selected_date}:",
            reply_markup=Calendar.get_time_keyboard()
        )
        
    elif action in ["prev", "next"]:
        # Навигация по месяцам
        _, _, year, month = callback.data.split("_")
        year, month = int(year), int(month)
        
        if action == "prev":
            if month == 1:
                year -= 1
                month = 12
            else:
                month -= 1
        else:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        
        await callback.message.edit_reply_markup(
            reply_markup=Calendar.get_calendar_keyboard(year, month)
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("time_select_"), ReservationStates.waiting_for_time)
async def process_time_selection(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Обработка выбора времени с проверкой доступности - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    selected_time = callback.data.replace("time_select_", "")
    data = await state.get_data()
    
    # Проверяем доступность через новый менеджер
    availability = await db_manager.check_table_availability(
        data['selected_date'], selected_time, data.get('guests_count', 1)
    )
    
    if not availability["available"]:
        # Используем новую систему ошибок
        from src.utils.reservation_errors import get_reservation_error_message, ReservationError
        
        error_mapping = {
            "restaurant_closed": ReservationError.RESTAURANT_CLOSED,
            "past_date": ReservationError.PAST_DATE,
            "no_tables": ReservationError.NO_TABLES,
            "capacity_exceeded": ReservationError.CAPACITY_EXCEEDED,
            "invalid_guests_count": ReservationError.INVALID_GUESTS,
            "error": ReservationError.SERVICE_UNAVAILABLE
        }
        
        error_type = error_mapping.get(availability['reason'], ReservationError.SERVICE_UNAVAILABLE)
        error_message = get_reservation_error_message(error_type, availability.get('details'))
        
        await callback.message.edit_text(error_message)
        await callback.answer()
        return
    
    # Продолжаем как раньше...
    await state.update_data(selected_time=selected_time)
    
    if data.get('guests_count'):
        await state.set_state(ReservationStates.waiting_for_name)
        await callback.message.edit_text(
            "👤 Введите ваше имя:",
            reply_markup=get_cancel_keyboard(l10n)
        )
    else:
        await state.set_state(ReservationStates.waiting_for_guests)
        await callback.message.edit_text(
            "👥 На сколько гостей бронируем?",
            reply_markup=get_guests_keyboard()
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("guests_"), ReservationStates.waiting_for_guests)
async def process_guests_count_callback(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Обработка выбора количества гостей - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    try:
        guests = int(callback.data.replace("guests_", ""))
        
        data = await state.get_data()
        
        # Если время уже выбрано, проверяем доступность с новым количеством гостей
        if data.get('selected_time'):
            availability = await db_manager.check_table_availability(
                data['selected_date'], data['selected_time'], guests
            )
            
            if not availability["available"]:
                from src.utils.reservation_errors import get_reservation_error_message, ReservationError
                
                error_mapping = {
                    "restaurant_closed": ReservationError.RESTAURANT_CLOSED,
                    "past_date": ReservationError.PAST_DATE,
                    "no_tables": ReservationError.NO_TABLES,
                    "capacity_exceeded": ReservationError.CAPACITY_EXCEEDED,
                    "invalid_guests_count": ReservationError.INVALID_GUESTS,
                    "error": ReservationError.SERVICE_UNAVAILABLE
                }
                
                error_type = error_mapping.get(availability['reason'], ReservationError.SERVICE_UNAVAILABLE)
                error_message = get_reservation_error_message(error_type, availability.get('details'))
                
                await callback.message.edit_text(error_message)
                await callback.answer()
                return
        
        await state.update_data(guests_count=guests)
        await state.set_state(ReservationStates.waiting_for_name)
        
        await callback.message.edit_text(
            f"👥 Выбрано гостей: {guests}\n\n👤 Теперь введите ваше имя:",
            reply_markup=get_cancel_keyboard(l10n)
        )
        
        await callback.answer(f"✅ Выбрано {guests} гостей")
        
    except ValueError:
        await callback.answer("❌ Ошибка при выборе количества гостей")

@router.message(ReservationStates.waiting_for_guests, F.text)
async def process_guests_count_text(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Обработка ввода количества гостей текстом - ОБНОВЛЕННАЯ ВЕРСИЯ"""
    try:
        guests = int(message.text)
        if guests <= 0 or guests > 20:
            await message.answer("❌ Количество гостей должно быть от 1 до 20")
            return
        
        data = await state.get_data()
        
        # Если время уже выбрано, проверяем доступность
        if data.get('selected_time'):
            availability = await db_manager.check_table_availability(
                data['selected_date'], data['selected_time'], guests
            )
            
            if not availability["available"]:
                from src.utils.reservation_errors import get_reservation_error_message, ReservationError
                
                error_mapping = {
                    "restaurant_closed": ReservationError.RESTAURANT_CLOSED,
                    "past_date": ReservationError.PAST_DATE,
                    "no_tables": ReservationError.NO_TABLES,
                    "capacity_exceeded": ReservationError.CAPACITY_EXCEEDED,
                    "invalid_guests_count": ReservationError.INVALID_GUESTS,
                    "error": ReservationError.SERVICE_UNAVAILABLE
                }
                
                error_type = error_mapping.get(availability['reason'], ReservationError.SERVICE_UNAVAILABLE)
                error_message = get_reservation_error_message(error_type, availability.get('details'))
                
                await message.answer(error_message)
                return
        
        await state.update_data(guests_count=guests)
        await state.set_state(ReservationStates.waiting_for_name)
        
        await message.answer(
            "👤 Введите ваше имя:",
            reply_markup=get_cancel_keyboard(l10n)
        )
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число от 1 до 20 или используйте кнопки")

@router.message(ReservationStates.waiting_for_name, F.text)
async def process_customer_name(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Обработка ввода имени"""
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Имя должно содержать минимум 2 символа")
        return
        
    await state.update_data(customer_name=name)
    await state.set_state(ReservationStates.waiting_for_phone)
    
    await message.answer(
        "📞 Введите ваш телефон или нажмите кнопку ниже:",
        reply_markup=await kb.get_phone_keyboard_with_cancel(l10n)
    )

@router.message(ReservationStates.waiting_for_phone, F.contact)
async def process_contact(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Обработка отправки контакта"""
    contact = message.contact
    phone = contact.phone_number
    
    # Форматируем номер телефона (убираем + если есть)
    if phone.startswith('+'):
        phone = phone[1:]
    
    await state.update_data(customer_phone=phone)
    await show_reservation_summary(message, state, l10n)

@router.message(ReservationStates.waiting_for_phone, F.text)
async def process_customer_phone_text(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Обработка ввода телефона текстом"""
    # Проверяем, не нажата ли кнопка отмены
    if message.text == "❌ Отмена":
        await cancel_reservation(message, state, l10n)
        return
        
    phone = message.text.strip()
    
    # Простая валидация телефона
    if len(phone) < 5:
        await message.answer("❌ Пожалуйста, введите корректный номер телефона")
        return
        
    await state.update_data(customer_phone=phone)
    await show_reservation_summary(message, state, l10n)

@router.callback_query(F.data == "confirm_reservation", ReservationStates.confirmation)
async def confirm_reservation(callback: CallbackQuery, state: FSMContext, db_manager: DatabaseManager, l10n: FluentLocalization, bot: Bot):
    """Подтверждение и сохранение бронирования - ОБНОВЛЕННАЯ ВЕРСИЯ С ПРАВИЛЬНЫМ ВРЕМЕНЕМ"""
    data = await state.get_data()
    
    try:
        user = callback.from_user
        logger.info(f"🔄 Starting ATOMIC reservation process for user {user.id}")
        
        # Используем новый атомарный метод создания брони
        reservation_id = await db_manager.create_reservation(
            user_id=user.id,
            reservation_date=data['selected_date'],
            reservation_time=data['selected_time'],
            guests_count=data['guests_count'],
            customer_name=data['customer_name'],
            customer_phone=data['customer_phone']
        )
        
        if reservation_id:
            logger.info(f"✅ Reservation #{reservation_id} created successfully for user {user.id}")

            # ФОРМАТИРУЕМ ВРЕМЯ ДЛЯ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЮ
            from src.utils.time_utils import format_restaurant_time
            try:
                day, month, year = map(int, data['selected_date'].split('.'))
                hour, minute = map(int, data['selected_time'].split(':'))
                reservation_datetime = datetime(year, month, day, hour, minute)
                formatted_time = format_restaurant_time(reservation_datetime)
            except Exception as e:
                logger.error(f"❌ Error formatting time in user confirmation: {e}")
                formatted_time = data['selected_time']  # fallback

            # Логируем успешное создание брони
            if db_manager:
                await db_manager.add_user_action(
                    user_id=user.id,
                    action_type='reservation_created',
                    action_data={
                        'reservation_id': reservation_id,
                        'date': data['selected_date'],
                        'time': data['selected_time'],
                        'guests': data['guests_count']
                    }
                )
            
            # Отправляем подтверждение пользователю с ПРАВИЛЬНЫМ ВРЕМЕНЕМ
            success_text = f"""
✅ <b>Бронирование #{reservation_id} успешно создано!</b>

📅 <b>Дата:</b> {data['selected_date']}
🕐 <b>Время:</b> {formatted_time}
👥 <b>Гости:</b> {data['guests_count']}
👤 <b>Имя:</b> {data['customer_name']}
📞 <b>Телефон:</b> {data['customer_phone']}

Мы свяжемся с вами для подтверждения брони.
            """
            
            await callback.message.edit_text(
                success_text,
                parse_mode="HTML",
                reply_markup=None
            )
            
            # Отправляем главное меню
            keyboard = await kb.get_main_menu_keyboard(l10n, user.id)
            await callback.message.answer(
                "🏠 Возвращаемся в главное меню:",
                reply_markup=keyboard
            )
            
            # Уведомляем администраторов с ПРАВИЛЬНЫМ ВРЕМЕНЕМ
            reservation_data = {
                'id': reservation_id,
                'date': data['selected_date'],
                'time': data['selected_time'],  # Будет отформатировано в notify_admins_about_reservation
                'guests': data['guests_count'],
                'name': data['customer_name'],
                'phone': data['customer_phone'],
                'user_id': user.id,
                'username': user.username,
                'user_full_name': user.full_name
            }
            
            await notify_admins_about_reservation(bot, reservation_data, l10n)
            
        else:
            # Обработка случая, когда бронь не создалась
            logger.warning(f"⚠️ Reservation creation failed for user {user.id} - likely race condition")
            
            from src.utils.reservation_errors import get_reservation_error_message, ReservationError
            error_message = get_reservation_error_message(ReservationError.CONFLICT)
            
            await callback.message.edit_text(
                error_message,
                reply_markup=None
            )
            
            # Предлагаем выбрать другое время
            await callback.message.answer(
                "🕐 Пожалуйста, выберите другое время:",
                reply_markup=Calendar.get_time_keyboard()
            )
            await state.set_state(ReservationStates.waiting_for_time)
            return
            
    except Exception as e:
        logger.error(f"❌ Reservation error for user {callback.from_user.id}: {e}", exc_info=True)
        
        from src.utils.reservation_errors import get_reservation_error_message, ReservationError
        error_message = get_reservation_error_message(ReservationError.SERVICE_UNAVAILABLE)
        
        await callback.message.edit_text(
            error_message,
            reply_markup=None
        )
        
    finally:
        # Очищаем состояние только если бронь создана успешно
        if reservation_id:
            await state.clear()

# Обработчики навигации
@router.callback_query(F.data == "back_to_calendar", ReservationStates.waiting_for_time)
async def back_to_calendar(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization):
    """Возврат к выбору даты"""
    await state.set_state(ReservationStates.waiting_for_date)
    await callback.message.edit_text(
        "📅 Выберите дату бронирования:",
        reply_markup=Calendar.get_calendar_keyboard()
    )
    await callback.answer()
    

@router.callback_query(F.data == "cancel_reservation")
@router.message(Command("cancel"), StateFilter(ReservationStates))
async def cancel_reservation(message: Message | CallbackQuery, state: FSMContext, l10n: FluentLocalization):
    """Отмена бронирования"""
    await state.clear()
    
    text = "❌ Бронирование отменено."
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text)
        await message.answer()
    else:
        await message.answer(text)


@router.callback_query(F.data.startswith("cancel_reservation_"))
async def cancel_reservation_callback(callback: CallbackQuery, db_manager=None, bot=None):
    """Обработка отмены брони через кнопку в напоминании"""
    try:
        reservation_id = int(callback.data.split("_")[2])
        user_id = callback.from_user.id
        
        logger.info(f"🔄 User {user_id} cancelling reservation #{reservation_id}")
        
        # Получаем информацию о брони
        reservation = await db_manager.get_reservation_by_id(reservation_id)
        
        if not reservation:
            await callback.answer("❌ Бронь не найдена", show_alert=True)
            return
            
        # Проверяем, что бронь принадлежит пользователю
        if reservation['user_id'] != user_id:
            await callback.answer("❌ Вы не можете отменить чужую бронь", show_alert=True)
            return
            
        # Проверяем, что бронь еще не отменена или завершена
        if reservation['status'] in ['cancelled', 'completed']:
            await callback.answer("ℹ️ Эта бронь уже отменена или завершена", show_alert=True)
            return
            
        # Отменяем бронь
        success = await db_manager.update_reservation_status(reservation_id, "cancelled")
        
        if success:
            # Форматируем дату и время для сообщения
            reservation_date = reservation['reservation_date']
            reservation_time = reservation['reservation_time']
            
            if hasattr(reservation_date, 'strftime'):
                formatted_date = reservation_date.strftime("%d.%m.%Y")
            else:
                formatted_date = str(reservation_date)
                
            if hasattr(reservation_time, 'strftime'):
                formatted_time = reservation_time.strftime("%H:%M")
            else:
                formatted_time = str(reservation_time)
            
            # Обновляем сообщение с напоминанием - убираем кнопку
            try:
                await callback.message.edit_text(
                    f"❌ <b>Бронь отменена</b>\n\n"
                    f"Вы отменили бронь на {formatted_date} "
                    f"в {formatted_time}\n\n"
                    f"👥 Гости: {reservation['guests_count']}\n"
                    f"👤 Имя: {reservation['customer_name']}",
                    parse_mode="HTML",
                    reply_markup=None  # Убираем кнопку
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not edit reminder message: {e}")
                # Если не получилось редактировать, просто отправляем новое сообщение
                await callback.message.answer("✅ Бронь успешно отменена")
            
            await callback.answer("✅ Бронь отменена")
            
            # 🔔 УВЕДОМЛЯЕМ АДМИНИСТРАТОРОВ
            await notify_admins_about_cancellation(bot, db_manager, reservation, callback.from_user)
            
            logger.info(f"✅ Reservation #{reservation_id} cancelled by user {user_id}")
            
        else:
            await callback.answer("❌ Ошибка при отмене брони", show_alert=True)
            logger.error(f"❌ Failed to cancel reservation #{reservation_id}")
            
    except Exception as e:
        logger.error(f"❌ Error in cancel_reservation_callback: {e}")
        await callback.answer("❌ Произошла ошибка при отмене брони", show_alert=True)

async def notify_admins_about_cancellation(bot, db_manager, reservation, user):
    """Уведомление администраторов об отмене брони"""
    try:
        admins = await db_manager.get_admins()
        
        if not admins:
            logger.warning("⚠️ No admins found to notify about cancellation")
            return
        
        # Форматируем дату и время для уведомления
        reservation_date = reservation['reservation_date']
        reservation_time = reservation['reservation_time']
        
        if hasattr(reservation_date, 'strftime'):
            formatted_date = reservation_date.strftime("%d.%m.%Y")
        else:
            formatted_date = str(reservation_date)
            
        if hasattr(reservation_time, 'strftime'):
            formatted_time = reservation_time.strftime("%H:%M")
        else:
            formatted_time = str(reservation_time)
            
        cancellation_text = (
            f"❌ <b>БРОНЬ ОТМЕНЕНА ПОЛЬЗОВАТЕЛЕМ</b>\n\n"
            f"📅 <b>Дата:</b> {formatted_date}\n"
            f"🕐 <b>Время:</b> {formatted_time}\n"
            f"👥 <b>Гости:</b> {reservation['guests_count']}\n"
            f"👤 <b>Клиент:</b> {reservation['customer_name']}\n"
            f"📞 <b>Телефон:</b> {reservation['customer_phone']}\n"
            f"🆔 <b>ID пользователя:</b> {user.id}\n"
            f"🔍 <b>Username:</b> @{user.username if user.username else 'нет'}\n"
            f"🆔 <b>ID брони:</b> {reservation['id']}\n\n"
            f"#отмена_брони"
        )
        
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin['user_id'],
                    text=cancellation_text,
                    parse_mode="HTML"
                )
                logger.info(f"✅ Notified admin {admin['user_id']} about cancellation #{reservation['id']}")
            except Exception as e:
                logger.error(f"❌ Failed to notify admin {admin['user_id']}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Error notifying admins: {e}")