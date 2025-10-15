from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import StateFilter
from fluent.runtime import FluentLocalization
from functools import wraps

from src.utils.config import settings
import src.handlers.admin.keyboards as kb
from src.utils.logger import get_logger

router = Router()
logger = get_logger(__name__)


def admin_required(func):
    """Декоратор для проверки прав доступа (ТОЛЬКО админы) через базу данных"""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        db_manager = kwargs.get('db_manager')
        if not db_manager:
            await message.answer("❌ Система проверки прав недоступна")
            return
        
        # Гарантируем существование пользователя
        await db_manager.ensure_user_exists(
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        
        if not await db_manager.is_admin(message.from_user.id):
            await message.answer("❌ Эта команда доступна только администраторам.")
            return
        return await func(message, *args, **kwargs)
    return wrapper

def staff_required(func):
    """Декоратор для проверки прав доступа (админы или персонал) через базу данных"""
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        db_manager = kwargs.get('db_manager')
        if not db_manager:
            await message.answer("❌ Система проверки прав недоступна")
            return
        
        # Гарантируем существование пользователя
        await db_manager.ensure_user_exists(
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        
        if not await db_manager.is_staff(message.from_user.id):
            await message.answer("❌ У вас нет доступа к этой команде.")
            return
        return await func(message, *args, **kwargs)
    return wrapper

@router.message(F.text == "📊 Аналитика")
@admin_required
async def analytics_menu(message: Message, l10n: FluentLocalization, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    keyboard = await kb.get_analytics_keyboard(l10n)
    await message.answer("📊 <b>Панель аналитики</b>\n\nВыберите тип отчета:", 
                        reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "📊 Общая статистика")
@admin_required
async def general_stats(message: Message, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    stats = await db_manager.get_general_stats()
    
    text = f"""
📊 <b>ОБЩАЯ СТАТИСТИКА</b>

👥 <b>Пользователи:</b>
• Всего: {stats.get('total_users', 0)}
• Сегодня: {stats.get('new_users_today', 0)}
• За неделю: {stats.get('new_users_week', 0)}
• Активные (30 дн.): {stats.get('active_users', 0)}

📋 <b>Бронирования:</b>
• Всего: {stats.get('total_reservations', 0)}
• Сегодня: {stats.get('reservations_today', 0)}

👨‍💼 <b>Вызовы персонала:</b>
• Всего: {stats.get('total_staff_calls', 0)}
    """
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "👥 Анализ пользователей")
@admin_required
async def user_analytics(message: Message, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    demographics = await db_manager.get_user_demographics()
    growth = await db_manager.get_user_growth(7)
    
    text = "👥 <b>ДЕМОГРАФИКА ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    
    for row in demographics:
        sex_emoji = "👨" if row['sex'] == 'male' else "👩" if row['sex'] == 'female' else "❓"
        major_text = {
            'student': '🎓 Студент',
            'entrepreneur': '💰 Предприниматель', 
            'hire': '💼 Работает в найме',
            'frilans': '💻 Фрилансер'
        }.get(row['major'], row['major'])
        
        text += f"{sex_emoji} {major_text}: {row['count']} ({row['percentage']}%)\n"
    
    if growth:
        week_growth = growth[-1]['total_users'] - growth[0]['total_users']
        text += f"\n📈 Прирост за неделю: +{week_growth} пользователей"
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "🎯 Целевые сегменты")
@admin_required
async def target_segments(message: Message, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    segments = await db_manager.get_target_segments()
    
    text = f"""
🎯 <b>ЦЕЛЕВЫЕ СЕГМЕНТЫ ДЛЯ РАССЫЛОК</b>

<b>Основные группы:</b>
👨 Мужчины: {segments.get('male_count', 0)}
👩 Женщины: {segments.get('female_count', 0)}

🎓 Студенты: {segments.get('students_count', 0)}
💰 Предприниматели: {segments.get('entrepreneurs_count', 0)}  
💻 Фрилансеры: {segments.get('freelancers_count', 0)}
💼 Работающие по найму: {segments.get('employees_count', 0)}

<b>Целевые комбинации:</b>
👨💰 Мужчины-предприниматели: {segments.get('male_entrepreneurs', 0)}
👩🎓 Женщины-студентки: {segments.get('female_students', 0)}
👨💻 Мужчины-фрилансеры: {segments.get('male_freelancers', 0)}
    """
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📋 Бронирования")
@admin_required
async def reservation_analytics(message: Message, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    stats = await db_manager.get_reservation_stats()
    trends = await db_manager.get_reservation_trends(7)
    
    avg_guests = stats.get('avg_guests') or 0
    
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    text = f"""
📋 <b>АНАЛИТИКА БРОНИРОВАНИЙ</b>

<b>Общая статистика:</b>
• Всего бронирований: {stats.get('total_reservations', 0)}
• Среднее гостей: {avg_guests:.1f}
• Максимум гостей: {stats.get('max_guests', 0)}

<b>Статусы:</b>
✅ Подтвержденные: {stats.get('confirmed', 0)}
⏳ Ожидание: {stats.get('pending', 0)}  
❌ Отмененные: {stats.get('cancelled', 0)}
🎉 Завершенные: {stats.get('completed', 0)}

<b>Сегодня:</b> {stats.get('today_reservations', 0)} бронирований
<b>Популярный день:</b> {day_names[int(stats.get('most_popular_day', 0))] if stats.get('most_popular_day') else 'Нет данных'}
    """
    
    if trends:
        today_trend = trends[0]['reservations_count'] if trends else 0
        text += f"\n📈 <b>Тренд:</b> {today_trend} бронирований сегодня"
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "👨‍💼 Вызовы персонала")
@admin_required
async def staff_calls_analytics(message: Message, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    stats = await db_manager.get_staff_calls_stats()
    menu_views = await db_manager.get_popular_menu_categories()
    
    avg_time = stats.get('avg_completion_time_min') or 0
    
    text = f"""
👨‍💼 <b>АНАЛИТИКА ВЫЗОВОВ ПЕРСОНАЛА</b>

<b>Статистика вызовов:</b>
• Всего вызовов: {stats.get('total_calls', 0)}
• Ожидают: {stats.get('pending_calls', 0)}
• В работе: {stats.get('accepted_calls', 0)}
• Выполнено: {stats.get('completed_calls', 0)}

<b>Эффективность:</b>
• Среднее время: {avg_time:.1f} мин.
• Активный стол: #{stats.get('most_active_table', 'Нет данных')}
• Вызовы сегодня: {stats.get('today_calls', 0)}
    """
    
    if menu_views:
        text += "\n\n<b>📊 ПОПУЛЯРНОСТЬ МЕНЮ:</b>\n"
        for i, item in enumerate(menu_views[:5], 1):
            text += f"{i}. {item['category']}: {item['total_views']} просмотров\n"
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📈 Активность по дням")
@admin_required
async def daily_activity(message: Message, db_manager = None):
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
        
    activity = await db_manager.get_daily_activity(7)
    
    if not activity:
        await message.answer("📊 Нет данных об активности за последние 7 дней")
        return
    
    text = "📈 <b>АКТИВНОСТЬ ПО ДНЯМ (неделя)</b>\n\n"
    
    current_date = None
    for row in activity:
        if row['date'] != current_date:
            text += f"\n📅 <b>{row['date']}</b>\n"
            current_date = row['date']
        
        action_name = {
            'menu_view': '📋 Просмотр меню',
            'reservation': '💺 Бронирование',
            'staff_call': '👨‍💼 Вызов персонала',
            'start': '🚀 Старт бота',
            'main_menu_view': '🏠 Главное меню',
            'menu_open': '📃 Открытие меню',
            'menu_category_view': '🍽️ Просмотр категории',
            'staff_call_start': '👨‍💼 Начало вызова',
            'staff_call_confirmed': '✅ Подтверждение вызова',
            'reservation_start': '💺 Начало бронирования',
            'delivery_click': '🛵 Клик доставки',
            'invite_friend_click': '👥 Клик приглашения',
            'loyalty_program_click': '💳 Клик лояльности',
            'get_directions_click': '🗺️ Клик маршрута',
            'help_command': '❓ Команда помощи',
            'unknown_message': '❓ Неизвестное сообщение'
        }.get(row['action_type'], row['action_type'])
        
        text += f"   {action_name}: {row['actions_count']} ({row['unique_users']} пользователей)\n"
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "🔙 В главное меню")
async def back_to_main_menu(message: Message, l10n: FluentLocalization, db_manager = None):
    """Возврат в главное меню"""
    from src.handlers.user.message import show_main_menu
    await show_main_menu(message, l10n, db_manager)


@router.message(F.text == "📋 Брони сегодня")
@admin_required
async def today_reservations_report(message: Message, db_manager=None, bot=None):
    """Отчет по бронированиям на сегодня"""
    if not db_manager:
        await message.answer("❌ База данных недоступна")
        return
    
    try:
        processing_msg = await message.answer("📊 Формирую отчет по бронированиям...")
        
        today = datetime.now().strftime("%d.%m.%Y")
        reservations = await db_manager.get_reservations_for_date(today)
        
        if not reservations:
            await processing_msg.edit_text("📭 На сегодня бронирований нет")
            return
        
        reservations_dict = [dict(reservation) for reservation in reservations]
        
        # 🔥 ТЕКСТОВАЯ СВОДКА ДЛЯ БЫСТРОГО ПРОСМОТРА
        status_emojis = {
            'pending': '⏳',
            'confirmed': '✅', 
            'cancelled': '❌',
            'completed': '🎉'
        }
        
        status_counts = {}
        total_guests = 0
        
        for reservation in reservations_dict:
            status = reservation['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            total_guests += reservation['guests_count']
        
        # Формируем текстовую сводку
        summary_text = f"📋 <b>БРОНИРОВАНИЯ НА СЕГОДНЯ ({today})</b>\n\n"
        summary_text += f"📊 <b>Общая статистика:</b>\n"
        summary_text += f"• Всего бронирований: {len(reservations)}\n"
        summary_text += f"• Общее количество гостей: {total_guests}\n\n"
        
        summary_text += f"📈 <b>По статусам:</b>\n"
        for status, count in status_counts.items():
            emoji = status_emojis.get(status, '📝')
            status_name = {
                'pending': 'Ожидание',
                'confirmed': 'Подтверждено',
                'cancelled': 'Отменено', 
                'completed': 'Завершено'
            }.get(status, status)
            summary_text += f"• {emoji} {status_name}: {count}\n"
        
        # Ближайшие бронирования (первые 5)
        upcoming = sorted(
            [r for r in reservations_dict if r['status'] in ['pending', 'confirmed']],
            key=lambda x: x['reservation_time']
        )[:5]
        
        if upcoming:
            summary_text += f"\n🕐 <b>Ближайшие бронирования:</b>\n"
            for i, reservation in enumerate(upcoming, 1):
                time_str = reservation['reservation_time'].strftime("%H:%M") if hasattr(reservation['reservation_time'], 'strftime') else str(reservation['reservation_time'])
                summary_text += f"{i}. {time_str} - {reservation['customer_name']} ({reservation['guests_count']} чел.)\n"
        
        # Отправляем текстовую сводку
        await message.answer(summary_text, parse_mode="HTML")
        
        # Генерируем и отправляем Excel файл
        from src.utils.report_generator import ReportGenerator
        report_gen = ReportGenerator()
        
        file_path = await report_gen.generate_daily_reservations_report(reservations_dict)
        
        # 🔥 ИСПРАВЛЕННЫЙ КОД ДЛЯ ОТПРАВКИ ФАЙЛА
        try:
            # Создаем InputFile с правильным именем
            input_file = FSInputFile(
                path=file_path,
                filename=f"Бронирования_{datetime.now().strftime('%d.%m.%Y')}.xlsx"
            )
            
            # Отправляем файл
            await bot.send_document(
                chat_id=message.chat.id,
                document=input_file,
                caption="📎 <b>Подробный отчет в Excel</b>\n\n"
                       "💡 <i>Используйте фильтры в файле для анализа</i>",
                parse_mode="HTML"
            )
            
            logger.info(f"✅ Sent reservations report to admin {message.from_user.id}")
            
        except Exception as file_error:
            logger.error(f"❌ Failed to send document: {file_error}")
            await message.answer("❌ Ошибка при отправке файла")
            raise file_error
        finally:
            # Всегда очищаем временный файл
            report_gen.cleanup_file(file_path)
        
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"❌ Failed to generate reservations report: {e}", exc_info=True)
        await message.answer("❌ Ошибка при формировании отчета")


@router.message(F.text == "🏥 Health Monitor")
@admin_required
async def health_monitor(message: Message, db_manager=None, bot=None):
    """Мониторинг здоровья системы"""
    if not db_manager or not bot:
        await message.answer("❌ Система мониторинга недоступна")
        return
    
    try:
        from src.utils.health_monitor import HealthMonitor
        monitor = HealthMonitor(db_manager, bot)
        health_data = await monitor.perform_full_health_check()
        
        # Форматируем сообщение
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️", 
            "unhealthy": "❌"
        }
        
        text = f"🏥 <b>SYSTEM HEALTH MONITOR</b>\n\n"
        text += f"📊 <b>Overall Status:</b> {status_emoji[health_data['status'].value]} {health_data['status'].value.upper()}\n"
        text += f"🕐 <b>Last Check:</b> {health_data['timestamp'].strftime('%H:%M:%S')}\n\n"
        
        # Сводка
        summary = health_data['summary']
        text += f"<b>Summary:</b>\n"
        text += f"• ✅ Healthy: {summary['healthy_checks']}/{summary['total_checks']}\n"
        text += f"• ⚠️ Degraded: {summary['degraded_checks']}\n"
        text += f"• ❌ Unhealthy: {summary['unhealthy_checks']}\n"
        text += f"• 📈 Success Rate: {summary['success_rate']:.1f}%\n"
        text += f"• ⏱️ Avg Response: {summary['avg_response_time']:.3f}s\n\n"
        
        # Детали проверок
        text += "<b>Detailed Checks:</b>\n"
        for check in health_data['checks']:
            emoji = status_emoji.get(check['status'], '❓')
            response_time = f"{check['response_time']:.3f}s" if check['response_time'] > 0 else "N/A"
            text += f"{emoji} <b>{check['component']}</b> ({response_time}): {check['message']}\n"
        
        # Добавляем кнопку для обновления
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Refresh", callback_data="refresh_health")
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"Health monitor error: {e}")
        await message.answer(f"❌ Ошибка мониторинга: {str(e)}")