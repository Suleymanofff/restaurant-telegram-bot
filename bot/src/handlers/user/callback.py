from typing import List
from aiogram import Router, F
from aiogram.types import CallbackQuery
from fluent.runtime import FluentLocalization
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import src.handlers.user.keyboards as kb
from src.states.call_stuff import CallStaff
from src.states.greetings import Greeting
from src.utils.logger import get_logger

from src.utils.time_utils import format_restaurant_time

from datetime import datetime

router = Router()
logger = get_logger(__name__)

# Подтвердить вызов персонала
@router.callback_query(F.data == "confirm_staff_call")
async def confirm_staff_call(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization, db_manager=None, settings=None):
    await callback.answer()
    
    # Получаем данные из состояния
    data = await state.get_data()
    call_id = data.get('call_id')
    table_number = data.get('table_number')
    
    if not call_id:
        await callback.message.answer("❌ Ошибка: данные вызова не найдены")
        await state.clear()
        return

    # НЕ завершаем вызов, а только уведомляем официантов
    if db_manager:
        # Добавляем действие пользователя
        await db_manager.add_user_action(
            user_id=callback.from_user.id,
            action_type='staff_call_confirmed',
            action_data={'call_id': call_id, 'table_number': table_number}
        )
        
        # ✅ ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ ПЕРСОНАЛУ (но НЕ завершаем вызов)
        user = callback.from_user
        user_info = f"{user.full_name} (@{user.username})" if user.username else user.full_name
        
        # Теперь функция возвращает message_ids и время
        message_ids, call_time = await notify_staff_about_call(
            bot=callback.bot,
            table_number=table_number,
            user_info=user_info,
            call_id=call_id,
            db_manager=db_manager
        )
    
    text = l10n.format_value("staff-called-message")
    await callback.message.edit_text(text=text)
    await state.clear()

# Отменить вызов персонала
@router.callback_query(F.data == "cancel_staff_call")
async def cancel_staff_call(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization, db_manager = None):
    await callback.answer()
    
    # Получаем данные из состояния
    data = await state.get_data()
    call_id = data.get('call_id')
    table_number = data.get('table_number')
    
    # Обновляем статус вызова в БД на 'cancelled'
    if db_manager and call_id:
        # Добавляем метод для отмены вызова
        await db_manager.cancel_staff_call(call_id)
        await db_manager.add_user_action(
            user_id=callback.from_user.id,
            action_type='staff_call_cancelled',
            action_data={'call_id': call_id, 'table_number': table_number}
        )
    
    text = l10n.format_value("cancel-staff-call")
    await callback.message.edit_text(text=text)
    await state.clear()  # ✅ Очищаем состояние

# Когда пользователь выбрал что он парень или девушка
@router.callback_query(F.data.in_(["user_sex_male", "user_sex_female"]))
async def confirm_sex_and_ask_major(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization, db_manager = None):
    await callback.answer()

    # Сохраняем данные о поле пользователя
    sex = callback.data
    if sex == "user_sex_male":
        sex = "male"
        await state.update_data(sex=sex)
    else:
        sex = "female"
        await state.update_data(sex=sex)
    
    # Сохраняем пол пользователя в БД
    if db_manager:
        await db_manager.update_user_profile(
            user_id=callback.from_user.id,
            sex=sex,
            major='unknown'  # Пока неизвестно
        )
        await db_manager.add_user_action(
            user_id=callback.from_user.id,
            action_type='sex_selected',
            action_data={'sex': sex}
        )
    
    # Заменяем предыдущее сообщение, на такое же, но без кнопок, чтобы пользователь не менял свой выбор
    text_before = l10n.format_value("who-are-you")
    await callback.message.edit_text(text=text_before)

    text = l10n.format_value(
        "ask-major",
        {
            "sex": await get_ru_by_eng(sex)
        }
    )
    await callback.message.answer(text=text, reply_markup=await kb.get_user_major_kb(l10n))
    await state.set_state(Greeting.get_major)

@router.callback_query(Greeting.get_major, F.data.in_([
    "user_major_student", 
    "user_major_entrepreneur", 
    "user_major_hire", 
    "user_major_frilans"
]))
async def confirm_major_and_send_main_menu(callback: CallbackQuery, state: FSMContext, l10n: FluentLocalization, db_manager = None):
    await callback.answer()

    # Сохраняем данные о профессии пользователя
    major = callback.data
    if major == "user_major_student":
        major = "student"
        await state.update_data(major=major)
    elif major == "user_major_entrepreneur":
        major = "entrepreneur"
        await state.update_data(major=major)
    elif major == "user_major_hire":
        major = "hire"
        await state.update_data(major=major)
    elif major == "user_major_frilans":
        major = "frilans"
        await state.update_data(major=major)

    # Получаем пол из состояния
    user_data = await state.get_data()
    user_sex = user_data["sex"]
    
    # Сохраняем профиль пользователя в БД
    if db_manager:
        await db_manager.update_user_profile(
            user_id=callback.from_user.id,
            sex=user_sex,
            major=major
        )
        await db_manager.add_user_action(
            user_id=callback.from_user.id,
            action_type='major_selected',
            action_data={'major': major}
        )

    # Заменяем предыдущее сообщение, на такое же, но без кнопок, чтобы пользователь не менял свой выбор
    text_before = l10n.format_value(
        "ask-major",
        {
            "sex": await get_ru_by_eng(user_sex)
        }
    )
    await callback.message.edit_text(text=text_before)
    
    text = l10n.format_value(
        "messages-before-main-menu",
        {
            "major": await get_ru_by_eng(major)
        }
    )
    await callback.message.answer(text=text)

    # Открываем главное меню (БЕЗ установки состояния)
    welcome_text = l10n.format_value("main-menu-text")
    keyboard = await kb.get_main_menu_keyboard(l10n, user_id=callback.from_user.id)
    await callback.message.answer(welcome_text, reply_markup=keyboard)
    
    # Очищаем состояние после регистрации
    await state.clear()

async def get_ru_by_eng(sex: str) -> str:
    translations = {
        "male": "парень",
        "female": "девушка",
        "student": "студент",
        "entrepreneur": "предпрениматель",
        "hire": "Найм",
        "frilans": "фриланс",
    }

    return translations[sex].capitalize()


async def get_all_staff_users(db_manager):
    """Получение всех ID персонала из базы данных"""
    try:
        staff_users = await db_manager.get_staff()
        admin_users = await db_manager.get_admins()
        
        # Объединяем списки и убираем дубликаты
        all_staff = staff_users + admin_users
        staff_ids = list(set([user['user_id'] for user in all_staff]))
        return staff_ids
    except Exception as e:
        logger.error(f"❌ Ошибка при получении списка персонала: {e}")
        return []

async def notify_staff_about_call(bot, table_number: int, user_info: str, call_id: int, db_manager=None):
    """Уведомление всего персонала (админы + стафф) о новом вызове с HTML разметкой"""
    try:
        from src.utils.config import settings
        
        message_ids = {}
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Принять вызов", callback_data=f"accept_call_{call_id}")
        
        current_time = format_restaurant_time()
        
        message_text = (
            f"🆘 <b>НОВЫЙ ВЫЗОВ ПЕРСОНАЛА</b>\n\n"
            f"🪑 <b>Стол:</b> #{table_number}\n"
            f"👤 <b>Клиент:</b> {user_info}\n"
            f"⏰ <b>Время:</b> {current_time}\n"
            f"🆔 <b>ID вызова:</b> {call_id}\n\n"
            f"<i>Кто первый успеет - того и клиент!</i>"
        )
        
        # 🔥 ИСПРАВЛЕНИЕ: Получаем актуальный список персонала из БД, а не из .env
        if db_manager:
            staff_ids = await get_all_staff_users(db_manager)
            logger.info(f"👥 Актуальный ID персонала из БД для уведомления: {staff_ids}")
        else:
            # Fallback: используем статический список если db_manager не доступен
            staff_ids = [int(staff_id.strip()) for staff_id in settings.STAFF_IDS.split(",")]
            logger.info(f"👥 Используем статический ID персонала из settings: {staff_ids}")
        
        # Отправляем ВСЕМУ персоналу (админы + стафф)
        for staff_id in staff_ids:
            try:
                logger.info(f"📤 Отправка сообщения персоналу {staff_id}")
                message = await bot.send_message(
                    chat_id=staff_id,
                    text=message_text,
                    reply_markup=keyboard.as_markup(),
                    parse_mode="HTML"
                )
                message_ids[staff_id] = message.message_id
                logger.info(f"✅ Сообщение отправлено персоналу {staff_id}, message_id: {message.message_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки персоналу {staff_id}: {e}")
        
        logger.info(f"💾 Сохранение message_ids в БД: {message_ids}")
        
        # Сохраняем время вызова и информацию о клиенте в БД
        if db_manager:
            success = await db_manager.update_call_message_ids(call_id, message_ids)
            if success:
                logger.info(f"✅ Message_ids сохранены в БД для вызова #{call_id}")
            else:
                logger.error(f"❌ Ошибка сохранения message_ids в БД для вызова #{call_id}")
        else:
            logger.error(f"❌ DB manager не доступен для сохранения message_ids")
        
        return message_ids, current_time
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в notify_staff_about_call: {e}", exc_info=True)
        return {}, ""