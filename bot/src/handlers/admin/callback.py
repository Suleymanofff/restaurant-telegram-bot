from aiogram import Router, F
from aiogram.types import CallbackQuery
import logging
import json
from src.utils.time_utils import format_restaurant_time
from src.utils.config import settings
from functools import wraps

from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()
logger = logging.getLogger(__name__)

def staff_required_callback(func):
    """Декоратор для проверки прав доступа в callback хэндлерах (админы + стафф)"""
    @wraps(func)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        # Получаем db_manager из kwargs
        db_manager = kwargs.get('db_manager')
        if not db_manager:
            # Если db_manager не передан, пытаемся найти в других местах
            for arg in args:
                if hasattr(arg, 'is_staff'):
                    db_manager = arg
                    break
        
        if db_manager:
            # Используем динамическую проверку из базы данных
            if not await db_manager.is_staff(callback.from_user.id):
                await callback.answer("❌ У вас нет доступа к этой команде.", show_alert=True)
                return
        else:
            # Fallback: используем статическую проверку если db_manager не доступен
            if not settings.is_staff(callback.from_user.id):
                await callback.answer("❌ У вас нет доступа к этой команде.", show_alert=True)
                return
        return await func(callback, *args, **kwargs)
    return wrapper

async def notify_all_staff_call_accepted(bot, staff_name: str, staff_username: str, table_number: int, call_id: int, user_info: str, call_time: str, accepted_by_staff_id: int, original_message_ids: dict, db_manager=None):
    """Уведомляем всех официантов, что вызов принят с сохранением всех данных"""
    try:
        logger.info(f"🔔 Уведомление о принятии вызова #{call_id}. Принял: {staff_name} (ID: {accepted_by_staff_id})")
        logger.info(f"📋 Message IDs для обновления: {original_message_ids}")
        logger.info(f"🔍 Тип accepted_by_staff_id: {type(accepted_by_staff_id)}")
        
        # Получаем актуальный список персонала из базы данных
        if db_manager:
            try:
                staff_ids = await get_all_staff_users(db_manager)
                logger.info(f"👥 Актуальный список персонала из БД: {staff_ids}")
            except Exception as e:
                logger.error(f"❌ Ошибка получения списка персонала: {e}")
                staff_ids = []
        else:
            staff_ids = []
        
        # 🔥 ИСПРАВЛЕННЫЙ ТЕКСТ: Теперь user_info содержит информацию о клиенте
        base_text = (
            f"✅ <b>ВЫЗОВ ПРИНЯТ</b>\n"
            f"👨‍💼 <b>Принял:</b> {staff_name} (@{staff_username})\n\n"
            f"🪑 <b>Стол:</b> #{table_number}\n"
            f"👤 <b>Клиент:</b> {user_info}\n"  # 🔥 Теперь здесь информация о клиенте
            f"⏰ <b>Время вызова:</b> {call_time}\n"
            f"🆔 <b>ID вызова:</b> {call_id}\n\n"
            f"<i>Официант уже направляется к столу</i>"
        )
        
        # Обновляем сообщения у всех официантов
        update_count = 0
        for staff_id_str, message_id in original_message_ids.items():
            try:
                # Преобразуем строковый staff_id в int для сравнения
                staff_id_int = int(staff_id_str)
                
                # Проверяем, является ли пользователь еще персоналом
                if db_manager and staff_id_int not in staff_ids:
                    logger.info(f"⚠️ Пользователь {staff_id_int} больше не в персонале, пропускаем")
                    continue
                
                logger.info(f"🔄 Обновление сообщения для staff_id: {staff_id_str}->{staff_id_int}, message_id: {message_id}")
                logger.info(f"🔍 Сравнение: {staff_id_int} == {accepted_by_staff_id} -> {staff_id_int == accepted_by_staff_id}")
                
                # Если это тот официант, который принял вызов - даем кнопку завершения
                if staff_id_int == accepted_by_staff_id:
                    logger.info(f"🎯 Это принявший официант, добавляем кнопку завершения")
                    keyboard = InlineKeyboardBuilder()
                    keyboard.button(text="✅ Завершить вызов", callback_data=f"complete_call_{call_id}")
                    
                    updated_text = base_text + "\n\n<b>Нажмите 'Завершить' после обслуживания стола</b>"
                    
                    await bot.edit_message_text(
                        chat_id=staff_id_int,
                        message_id=message_id,
                        text=updated_text,
                        reply_markup=keyboard.as_markup(),
                        parse_mode="HTML"
                    )
                    logger.info(f"✅ Добавлена кнопку завершения для принявшего официанта")
                else:
                    # Для остальных - просто информация (без кнопок)
                    logger.info(f"📝 Это другой официант, убираем кнопки")
                    await bot.edit_message_text(
                        chat_id=staff_id_int,
                        message_id=message_id,
                        text=base_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )
                
                update_count += 1
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обновлении сообщения для staff {staff_id_str}: {e}")
        
        logger.info(f"✅ Успешно обновлено {update_count} сообщений из {len(original_message_ids)}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в notify_all_staff_call_accepted: {e}", exc_info=True)

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

@router.callback_query(F.data.startswith("accept_call_"))
@staff_required_callback
async def accept_staff_call(callback: CallbackQuery, db_manager=None, settings=None):
    """Обработка принятия вызова персоналом - ТОЛЬКО принятие, без завершения"""
    try:
        call_id = int(callback.data.split("_")[2])
        staff_id = callback.from_user.id
        staff_name = callback.from_user.full_name
        staff_username = callback.from_user.username
        
        logger.info(f"🔄 Начало принятия вызова #{call_id} персоналом {staff_name} (ID: {staff_id})")
        
        # Проверяем, не принят ли вызов уже другим официантом
        call = await db_manager.get_staff_call(call_id)
        if not call:
            logger.error(f"❌ Вызов #{call_id} не найден")
            await callback.answer("❌ Вызов не найден", show_alert=True)
            return

        logger.info(f"📊 Статус вызова #{call_id}: {call['status']}")
        
        if call['status'] != 'pending':
            logger.warning(f"⚠️ Вызов #{call_id} уже принят. Текущий статус: {call['status']}")
            await callback.answer("❌ Этот вызов уже принят другим официантом", show_alert=True)
            return
        
        # Принимаем вызов (меняем статус на 'accepted')
        success = await db_manager.accept_staff_call(call_id, staff_id, staff_name)
        if not success:
            logger.error(f"❌ Не удалось принять вызов #{call_id} в БД")
            await callback.answer("❌ Не удалось принять вызов", show_alert=True)
            return
        
        logger.info(f"✅ Вызов #{call_id} принят в БД")
        
        # Получаем message_ids из БД
        message_ids = {}
        if call.get('message_ids'):
            try:
                if isinstance(call['message_ids'], str):
                    message_ids = json.loads(call['message_ids'])
                else:
                    message_ids = call['message_ids']
                
                logger.info(f"📨 Получены message_ids для вызова #{call_id}: {message_ids}")
                logger.info(f"🔍 Типы ключей: {[type(k) for k in message_ids.keys()]}")
                
            except Exception as e:
                logger.error(f"❌ Failed to parse message_ids for call {call_id}: {e}")
        else:
            logger.warning(f"⚠️ Нет message_ids для вызова #{call_id}")
        
        
        user_info = await get_client_info_for_call(call, db_manager)
        
        # Получаем время создания вызова
        call_time = format_restaurant_time(call['created_at']) if call.get('created_at') else "Неизвестно"
        
        # Уведомляем всех официантов об принятии вызова
        if message_ids:
            logger.info(f"🔔 Начинаем уведомление персонала о принятии вызова #{call_id}")
            await notify_all_staff_call_accepted(
                bot=callback.bot,
                staff_name=staff_name,
                staff_username=staff_username,
                table_number=call['table_number'],
                call_id=call_id,
                user_info=user_info,
                call_time=call_time,
                accepted_by_staff_id=staff_id,
                original_message_ids=message_ids,
                db_manager=db_manager  # Передаем db_manager для проверки актуального персонала
            )
            logger.info(f"✅ Уведомления отправлены для вызова #{call_id}")
        else:
            logger.error(f"❌ Не могу уведомить персонала - нет message_ids для вызова #{call_id}")
        
        await callback.answer(f"✅ Вы приняли вызов стола #{call['table_number']}", show_alert=True)
        logger.info(f"🎯 Вызов стола #{call['table_number']} принят персоналом {staff_name}")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в accept_staff_call: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при принятии вызова", show_alert=True)

async def get_client_info_for_call(call: dict, db_manager) -> str:
    """Получение информации о клиенте для вызова персонала"""
    try:
        # Получаем информацию о пользователе из базы данных
        user = await db_manager.get_user(call['user_id'])
        
        if user:
            # Формируем информацию о клиенте
            client_info = user.get('full_name', 'Неизвестный клиент')
            
            # Добавляем username, если есть
            if user.get('username'):
                client_info += f" (@{user['username']})"
            
            # Добавляем демографическую информацию, если есть
            demographics = []
            if user.get('sex') and user['sex'] != 'unknown':
                sex_display = {
                    'male': '👨',
                    'female': '👩', 
                    'other': '👤'
                }.get(user['sex'], '👤')
                demographics.append(sex_display)
            
            if user.get('major') and user['major'] != 'unknown':
                major_display = {
                    'student': '🎓',
                    'entrepreneur': '💼',
                    'hire': '💻', 
                    'frilans': '🚀'
                }.get(user['major'], '👤')
                demographics.append(major_display)
            
            if demographics:
                client_info += f" {''.join(demographics)}"
            
            logger.info(f"👤 Получена информация о клиенте: {client_info}")
            return client_info
        else:
            logger.warning(f"⚠️ Пользователь {call['user_id']} не найден в БД")
            return "Неизвестный клиент"
            
    except Exception as e:
        logger.error(f"❌ Ошибка при получении информации о клиенте: {e}")
        return "Клиент"

@router.callback_query(F.data.startswith("complete_call_"))
@staff_required_callback
async def complete_staff_call(callback: CallbackQuery, db_manager=None):
    """Завершение вызова персоналом"""
    try:
        call_id = int(callback.data.split("_")[2])
        staff_id = callback.from_user.id
        
        logger.info(f"🔄 Завершение вызова #{call_id} персоналом {staff_id}")
        
        # Проверяем, что вызов принят этим официантом
        call = await db_manager.get_staff_call(call_id)
        if not call:
            await callback.answer("❌ Вызов не найден", show_alert=True)
            return
            
        # 🔥 Проверяем, что вызов принят этим официантом (учитываем типы данных)
        accepted_by = call.get('accepted_by')
        if call['status'] != 'accepted' or accepted_by != staff_id:
            logger.warning(f"⚠️ Попытка завершения чужого вызова: accepted_by={accepted_by}, staff_id={staff_id}")
            await callback.answer("❌ Вы не принимали этот вызов", show_alert=True)
            return

        # Завершаем вызов
        success = await db_manager.complete_staff_call(call_id)
        if success:
            # Обновляем сообщение у официанта
            await callback.message.edit_text(
                f"✅ Вызов стола #{call['table_number']} завершен",
                parse_mode="Markdown"
            )
            await callback.answer("✅ Вызов завершен")
            logger.info(f"✅ Вызов #{call_id} завершен")
        else:
            await callback.answer("❌ Не удалось завершить вызов", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ Error in complete_staff_call: {e}")
        await callback.answer("❌ Произошла ошибка при завершении вызова", show_alert=True)

@router.callback_query(F.data.startswith("cancel_call_"))
@staff_required_callback
async def cancel_staff_call(callback: CallbackQuery, db_manager = None):
    """Обработка отмены вызова персоналом"""
    try:
        call_id = int(callback.data.split("_")[2])
        
        success = await db_manager.cancel_staff_call(call_id)
        if success:
            await callback.answer("✅ Вызов отменен", show_alert=True)
        else:
            await callback.answer("❌ Не удалось отменить вызов", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ Error in cancel_staff_call: {e}")
        await callback.answer("❌ Произошла ошибка при отмене вызова", show_alert=True)

@router.callback_query(F.data == "refresh_health")
@staff_required_callback
async def refresh_health_check(callback: CallbackQuery, db_manager=None, bot=None):
    """Обновление проверки здоровья"""
    try:
        from src.utils.health_monitor import HealthMonitor
        monitor = HealthMonitor(db_manager, bot)
        health_data = await monitor.perform_full_health_check()
        
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️", 
            "unhealthy": "❌"
        }
        
        text = f"🏥 <b>SYSTEM HEALTH MONITOR</b> (Updated)\n\n"
        text += f"📊 <b>Overall Status:</b> {status_emoji[health_data['status'].value]} {health_data['status'].value.upper()}\n"
        text += f"🕐 <b>Last Check:</b> {health_data['timestamp'].strftime('%H:%M:%S')}\n\n"
        
        # Обновляем сообщение
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer("✅ Health check refreshed")
        
    except Exception as e:
        await callback.answer("❌ Failed to refresh health check", show_alert=True)