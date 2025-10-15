from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import logging
import re

from src.database.db_manager import DatabaseManager
from src.utils.config import settings
from fluent.runtime import FluentLocalization

router = Router()
logger = logging.getLogger(__name__)


# helper: считаем длину caption без HTML тегов (для ограничения Telegram ~1024 символа)
def _strip_html_tags(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text)

def _caption_too_long(text: str, limit: int = 1024) -> bool:
    # считаем длину без HTML тегов (Telegram считает символы без тегов)
    return len(_strip_html_tags(text)) > limit


class DeliveryDashboard:
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    async def get_dashboard_stats(self):
        """Получение статистики для дашборда с правильными суммами"""
        stats = {
            'today': 0,
            'pending': 0,
            'preparing': 0,
            'on_way': 0,
            'delivered': 0,
            'urgent': 0,
            'total_revenue': 0,  # Добавляем общую выручку
            'total_discounts': 0,  # Добавляем общие скидки
        }
        
        try:
            # Получаем заказы за сегодня
            today_orders = await self.db_manager.get_delivery_orders_today()
            stats['today'] = len(today_orders)
            
            # Считаем по статусам и суммам
            for order in today_orders:
                status = order['status']
                if status in stats:
                    stats[status] += 1
                
                # Считаем выручку для доставленных заказов
                if status in ['delivered', 'completed']:
                    stats['total_revenue'] += order.get('final_amount', 0)
                
                # Считаем общие скидки
                stats['total_discounts'] += order.get('discount_amount', 0)
            
            # Срочные заказы (менее 30 минут)
            from datetime import datetime, timezone
            now_utc = datetime.now(timezone.utc)
            
            urgent_orders = []
            for order in today_orders:
                if order['status'] in ['pending', 'preparing']:
                    created_at = order['created_at']
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    
                    time_diff = (now_utc - created_at).total_seconds()
                    if time_diff < 1800:  # 30 минут
                        urgent_orders.append(order)
            
            stats['urgent'] = len(urgent_orders)
            
        except Exception as e:
            logger.error(f"❌ Error getting dashboard stats: {e}")
        
        return stats
    
    async def format_dashboard_message(self, stats, urgent_orders, active_orders):
        """Форматирование сообщения дашборда с правильными суммами"""
        
        message = "🛵 <b>ПАНЕЛЬ УПРАВЛЕНИЯ ДОСТАВКОЙ</b>\n\n"
        
        # Статистика с выручкой
        message += f"📊 <b>СЕГОДНЯ:</b> {stats['today']} заказов\n"
        message += f"⏳ Ожидают: {stats['pending']} | 👨‍🍳 Готовятся: {stats['preparing']} | "
        message += f"🚗 В пути: {stats['on_way']} | ✅ Завершены: {stats['delivered']}\n"
        
        if stats['total_revenue'] > 0:
            message += f"💰 <b>Выручка за сегодня:</b> {stats['total_revenue']}₽\n"
        
        if stats['total_discounts'] > 0:
            message += f"🎁 <b>Предоставлено скидок:</b> -{stats['total_discounts']}₽\n"
        
        message += "\n"
        
        # Срочные заказы
        if urgent_orders:
            message += "🔥 <b>СРОЧНЫЕ ЗАКАЗЫ (менее 30 минут):</b>\n"
            message += "──────────────────────────────\n"
            
            for order in urgent_orders:  # БЕЗ ограничения
                message += await self.format_order_card(order, urgent=True)
                message += "\n"
        else:
            message += "✅ <b>Срочных заказов нет</b>\n\n"
        
        # Активные заказы - БЕЗ ограничения [:5]
        if active_orders:
            message += "📋 <b>ВСЕ АКТИВНЫЕ ЗАКАЗЫ:</b>\n"
            message += "──────────────────────────────\n"
            
            for order in active_orders:  # БЕЗ ограничения
                message += await self.format_order_card(order, urgent=False)
                message += "\n"
        
        return message
    
    async def format_order_card(self, order, urgent=False):
        """Форматирование карточки заказа с указанием количества блюд и типа оплаты"""
        time_ago = self.get_time_ago(order['created_at'])
        phone_masked = self.mask_phone(order.get('customer_phone', '—'))

        card = ""
        if urgent:
            card += "🆕 "
        else:
            status_emoji = {
                'pending': '⏳',
                'preparing': '👨‍🍳',
                'on_way': '🚗',
                'delivered': '✅'
            }.get(order.get('status'), '📦')
            card += f"{status_emoji} "

        # Заголовок: id, время, имя, телефон, время с момента
        created_at = order.get('created_at')
        created_time_str = created_at.strftime('%H:%M') if created_at else "—:—"
        card += f"<b>#{order.get('id')}</b> | {created_time_str} | "
        card += f"{order.get('customer_name', '—')} 📞 {phone_masked} | {time_ago}\n"

        try:
            # Получаем order_data (поддерживаем строку JSON и dict)
            order_data = order.get('order_data', {}) or {}
            if isinstance(order_data, str):
                import json
                try:
                    order_data = json.loads(order_data)
                except Exception:
                    order_data = {}

            items = order_data.get('items', []) if isinstance(order_data, dict) else []

            # Формируем краткий список позиций с количествами: "Пицца x2, Салат x1"
            item_lines = []
            for it in items:
                try:
                    name = it.get('name', '—')
                    qty = it.get('quantity', 1)
                    item_lines.append(f"{name} x{qty}")
                except Exception:
                    continue

            if item_lines:
                # Показываем до 2 позиций + "и ещё N"
                preview = ", ".join(item_lines[:2])
                if len(item_lines) > 2:
                    preview += f" и ещё {len(item_lines) - 2}"
                card += f"   {preview}"
            else:
                card += "   Состав заказа не доступен"

            # Сумма: старая/новая + инфо о скидках/бонусах
            final_amount = order.get('final_amount')
            total_amount = order.get('total_amount', 0) or 0

            if final_amount and final_amount != total_amount:
                card += f" | <s>{int(total_amount)}₽</s> <b>{int(final_amount)}₽</b>"
                discount_info = []
                if order.get('discount_amount', 0) > 0:
                    discount_info.append(f"🎁 -{int(order['discount_amount'])}₽")
                if order.get('bonus_used', 0) > 0:
                    discount_info.append(f"💎 -{int(order['bonus_used'])}₽")
                if discount_info:
                    card += f" ({' '.join(discount_info)})"
            else:
                amount_to_show = int(final_amount) if final_amount is not None else int(total_amount)
                card += f" | {amount_to_show}₽"

            card += "\n"

            # Если срочный — покажем короткий адрес
            if urgent:
                addr = order.get('delivery_address', '') or ''
                short_addr = (addr[:30] + '...') if len(addr) > 30 else addr
                card += f"   🏠 {short_addr}\n"

            # Добавляем информацию о типе оплаты и статусе оплаты
            payment_method = order.get('payment_method') or (order_data.get('payment_method') if isinstance(order_data, dict) else None) or '—'
            payment_status = order.get('payment_status') or '—'
            card += f"   💳 Оплата: {payment_method} ({payment_status})\n"

        except Exception as e:
            logger.error(f"❌ Error formatting order items: {e}")
            card += "   Состав заказа не доступен\n"

        return card
    
    def get_time_ago(self, created_at):
        """Время с момента создания заказа"""
        from datetime import datetime, timezone
        
        try:
            now = datetime.now(timezone.utc)
            
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            diff = now - created_at
            minutes = int(diff.total_seconds() / 60)
            
            if minutes < 1:
                return "только что"
            elif minutes < 60:
                return f"{minutes} мин назад"
            else:
                hours = minutes // 60
                return f"{hours} ч назад"
                
        except Exception as e:
            logger.error(f"❌ Error in get_time_ago: {e}")
            return "неизвестно"
    
    def mask_phone(self, phone):
        """Маскировка номера телефона"""
        phone_str = str(phone)
        if len(phone_str) >= 6:
            return phone_str[:4] + '***' + phone_str[-2:]
        return phone_str
    
    async def get_dashboard_keyboard(self, orders):
        """Клавиатура для дашборда - кнопки для ВСЕХ активных заказов"""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для ВСЕХ активных заказов (не только срочных)
        active_orders = [o for o in orders if o['status'] in ['pending', 'preparing', 'on_way']]
        
        for order in active_orders:  # БЕЗ ограничения
            if order['status'] == 'pending':
                builder.row(
                    InlineKeyboardButton(
                        text=f"👨‍🍳 Начать #{order['id']}",
                        callback_data=f"dashboard_start_{order['id']}"
                    ),
                    InlineKeyboardButton(
                        text=f"📞 #{order['id']}",
                        callback_data=f"dashboard_call_{order['id']}"
                    )
                )
            elif order['status'] == 'preparing':
                builder.row(
                    InlineKeyboardButton(
                        text=f"🚗 В путь #{order['id']}",
                        callback_data=f"dashboard_ship_{order['id']}"
                    ),
                    InlineKeyboardButton(
                        text=f"📞 #{order['id']}",
                        callback_data=f"dashboard_call_{order['id']}"
                    )
                )
            elif order['status'] == 'on_way':
                builder.row(
                    InlineKeyboardButton(
                        text=f"✅ Доставлен #{order['id']}",
                        callback_data=f"dashboard_delivered_{order['id']}"
                    ),
                    InlineKeyboardButton(
                        text=f"📞 #{order['id']}",
                        callback_data=f"dashboard_call_{order['id']}"
                    )
                )
        
        # Общие кнопки
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить", callback_data="dashboard_refresh"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="dashboard_stats")
        )
        
        return builder.as_markup()

async def refresh_dashboard(message: Message, db_manager: DatabaseManager):
    """Обновление дашборда — теперь через safe_refresh_dashboard, чтобы не падать на фото/документах."""
    try:
        dashboard = DeliveryDashboard(db_manager)

        stats = await dashboard.get_dashboard_stats()
        all_orders = await db_manager.get_all_delivery_orders()

        urgent_orders = [o for o in all_orders if o['status'] in ['pending', 'preparing']]
        active_orders = [o for o in all_orders if o['status'] in ['pending', 'preparing', 'on_way']]

        text = await dashboard.format_dashboard_message(stats, urgent_orders, active_orders)
        keyboard = await dashboard.get_dashboard_keyboard(active_orders)

        # Используем safe_refresh_dashboard — она умеет работать с сообщениями-изображениями
        try:
            await safe_refresh_dashboard(bot=message.bot, message=message, new_text=text, new_kb=keyboard)
        except Exception as e:
            # Логируем и как последний фоллбек пробуем старый подход (как раньше)
            logger.exception(f"refresh_dashboard: safe_refresh_dashboard failed: {e}")
            try:
                await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            except Exception as edit_error:
                if "message is not modified" not in str(edit_error):
                    logger.exception(f"refresh_dashboard: fallback edit_text also failed: {edit_error}")
    except Exception as e:
        logger.error(f"❌ Error refreshing dashboard: {e}")



async def safe_refresh_dashboard(bot: Bot, message: Message, new_text: str, new_kb=None, parse_mode="HTML"):
    """
    Универсальная, устойчивая функция обновления админского сообщения:
    - если сообщение — фото/document/media_group -> пытаемся edit_message_caption (если в лимите)
      иначе -> delete + send_message
    - если сообщение текстовое -> edit_message_text
    - fallback -> delete + send_message
    """
    chat_id = message.chat.id
    message_id = message.message_id

    # подготовка reply_markup (InlineKeyboardBuilder или InlineKeyboardMarkup)
    reply_markup = None
    if new_kb is not None:
        try:
            reply_markup = new_kb.as_markup() if hasattr(new_kb, "as_markup") else new_kb
        except Exception:
            reply_markup = new_kb

    # флаги наличия контента
    has_photo = bool(getattr(message, "photo", None))
    has_document = getattr(message, "document", None) is not None
    has_media_group = getattr(message, "media_group_id", None) is not None
    has_caption = getattr(message, "caption", None) is not None
    has_text = getattr(message, "text", None) is not None

    logger.debug(f"safe_refresh_dashboard: msg_id={message_id} has_photo={has_photo} has_document={has_document} "
                 f"has_media_group={has_media_group} has_caption={bool(has_caption)} has_text={bool(has_text)}")

    # 1) Если сообщение содержит медиа (photo/document/media_group) — пробуем редактировать caption
    try:
        if has_photo or has_document or has_media_group:
            # если caption не слишком длинный — пробуем edit_message_caption
            if not _caption_too_long(new_text, limit=1024):
                try:
                    await bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=new_text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                    logger.debug("safe_refresh_dashboard: used edit_message_caption")
                    return True
                except Exception as e:
                    logger.debug(f"safe_refresh_dashboard: edit_message_caption failed: {e}")

            # либо caption слишком длинный, либо edit упал -> удаляем старое медиа и отправляем новое текстовое сообщение
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.debug(f"safe_refresh_dashboard: failed to delete old media message: {e}")

            await bot.send_message(chat_id=chat_id, text=new_text, parse_mode=parse_mode, reply_markup=reply_markup)
            logger.debug("safe_refresh_dashboard: deleted media and sent text message fallback")
            return True

        # 2) Если сообщение было обычным текстом — пробуем edit_message_text
        if has_text:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                logger.debug("safe_refresh_dashboard: used edit_message_text")
                return True
            except Exception as e:
                # если сообщение не изменилось — это не ошибка
                if "message is not modified" in str(e):
                    return True
                logger.debug(f"safe_refresh_dashboard: edit_message_text failed: {e}")

        # 3) Фоллбек: удаляем и отправляем новое сообщение
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.debug(f"safe_refresh_dashboard: delete_message fallback failed: {e}")

        await bot.send_message(chat_id=chat_id, text=new_text, parse_mode=parse_mode, reply_markup=reply_markup)
        logger.debug("safe_refresh_dashboard: final fallback sent new text message")
        return True

    except Exception as final_e:
        logger.exception(f"safe_refresh_dashboard: final fallback failed: {final_e}")
        return False

async def show_delivery_stats(message: Message, db_manager: DatabaseManager):
    """Показать статистику доставки с ПРАВИЛЬНЫМ расчетом выручки"""
    dashboard = DeliveryDashboard(db_manager)
    
    today_orders = await db_manager.get_delivery_orders_today()
    
    stats_text = "📊 <b>СТАТИСТИКА ДОСТАВКИ</b>\n\n"
    
    if today_orders:
        total_orders = len(today_orders)
        completed_orders = len([o for o in today_orders if o['status'] == 'delivered'])
        
        # 🔥 ПРАВИЛЬНЫЙ РАСЧЕТ ВЫРУЧКИ - используем final_amount для завершенных заказов
        total_revenue = sum(o['final_amount'] for o in today_orders if o['status'] in ['delivered', 'completed'])
        
        # Общая сумма всех заказов за сегодня (по final_amount)
        total_amount_all = sum(o['final_amount'] for o in today_orders)
        
        # Сумма примененных скидок и бонусов
        total_discounts = sum(o.get('discount_amount', 0) for o in today_orders)
        total_bonus_used = sum(o.get('bonus_used', 0) for o in today_orders)
        
        stats_text += f"📦 <b>Заказов сегодня:</b> {total_orders}\n"
        stats_text += f"✅ <b>Доставлено:</b> {completed_orders}\n"
        stats_text += f"💰 <b>Выручка (доставлено):</b> {total_revenue}₽\n"
        stats_text += f"💳 <b>Общая сумма заказов:</b> {total_amount_all}₽\n"
        
        if total_discounts > 0:
            stats_text += f"🎁 <b>Всего скидок:</b> -{total_discounts}₽\n"
        
        if total_bonus_used > 0:
            stats_text += f"💎 <b>Использовано бонусов:</b> -{total_bonus_used}₽\n"
        
        if total_orders > 0:
            conversion_rate = (completed_orders / total_orders) * 100
            stats_text += f"📈 <b>Конверсия:</b> {conversion_rate:.1f}%\n"
        else:
            stats_text += "📈 <b>Конверсия:</b> 0%\n"
            
        # Статистика по статусам
        status_counts = {}
        for order in today_orders:
            status = order['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
        stats_text += f"\n<b>По статусам:</b>\n"
        for status, count in status_counts.items():
            status_emoji = {
                'pending': '⏳',
                'preparing': '👨‍🍳',
                'on_way': '🚗',
                'delivered': '✅',
                'cancelled': '❌'
            }.get(status, '📦')
            stats_text += f"{status_emoji} {status}: {count}\n"
            
    else:
        stats_text += "📭 Заказов сегодня нет\n"
    
    await message.answer(stats_text, parse_mode="HTML")

@router.message(F.text == "📦 Управление доставкой")
async def delivery_dashboard_admin(message: Message, db_manager: DatabaseManager, l10n: FluentLocalization):
    """Главная панель управления доставкой для АДМИНОВ"""
    if not await db_manager.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для управления заказами")
        return
    
    dashboard = DeliveryDashboard(db_manager)
    
    stats = await dashboard.get_dashboard_stats()
    all_orders = await db_manager.get_all_delivery_orders()
    
    urgent_orders = [o for o in all_orders if o['status'] in ['pending', 'preparing']]
    active_orders = [o for o in all_orders if o['status'] in ['pending', 'preparing', 'on_way']]
    
    text = await dashboard.format_dashboard_message(stats, urgent_orders, active_orders)
    keyboard = await dashboard.get_dashboard_keyboard(active_orders)
    
    await message.answer("📦 Загрузка панели доставки...", reply_markup=ReplyKeyboardRemove())
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data.startswith("dashboard_"))
async def handle_dashboard_actions(callback: CallbackQuery, db_manager: DatabaseManager, bot: Bot):
    """Обработка действий на дашборде"""
    action = callback.data.split("_")[1]
    order_id = int(callback.data.split("_")[2]) if len(callback.data.split("_")) > 2 else None
    
    try:
        if action == "start" and order_id:
            success = await db_manager.update_delivery_order_status(order_id, "preparing")
            if success:
                await callback.answer("✅ Заказ взят в работу")
                await refresh_dashboard(callback.message, db_manager)
            else:
                await callback.answer("❌ Ошибка при обновлении статуса")
        
        elif action == "ship" and order_id:
            success = await db_manager.update_delivery_order_status(order_id, "on_way")
            if success:
                await callback.answer("🚗 Заказ передан курьеру")
                await refresh_dashboard(callback.message, db_manager)
            else:
                await callback.answer("❌ Ошибка при обновлении статуса")
        
        elif action == "call" and order_id:
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order:
                await callback.answer(f"📞 Телефон: {order['customer_phone']}", show_alert=True)
            else:
                await callback.answer("❌ Заказ не найден")
        
        elif action == "refresh":
            await refresh_dashboard(callback.message, db_manager)
            await callback.answer("🔄 Обновлено")
        
        elif action == "stats":
            await show_delivery_stats(callback.message, db_manager)
            await callback.answer()
        
        elif action == "delivered" and order_id:
            success = await db_manager.update_delivery_order_status(order_id, "delivered")
            if success:
                await callback.answer("✅ Заказ доставлен")
                await refresh_dashboard(callback.message, db_manager)
            else:
                await callback.answer("❌ Ошибка при обновлении статуса")
            
    except Exception as e:
        logger.error(f"❌ Dashboard action error: {e}")
        await callback.answer("❌ Ошибка при выполнении действия")


@router.callback_query(F.data.startswith("payment_confirm_"))
async def admin_handle_payment_confirm(callback: CallbackQuery, db_manager: DatabaseManager, bot: Bot):
    """Админ подтвердил оплату -> обновляем карточку: показываем только кнопку 'В приготовление'"""
    try:
        admin_id = callback.from_user.id
        admin_ids = [int(a.strip()) for a in settings.ADMIN_IDS.split(",") if a.strip()]
        if admin_id not in admin_ids:
            await callback.answer("❌ У вас нет прав для этого действия.", show_alert=True)
            return

        # Парсим order_id
        try:
            order_id = int(callback.data.split("payment_confirm_")[-1])
        except Exception:
            await callback.answer("❌ Неверный формат callback.", show_alert=True)
            logger.warning(f"Bad callback data for payment_confirm: {callback.data}")
            return

        # 1) Подтверждаем оплату в БД (атомарно)
        ok = await db_manager.confirm_payment(order_id, confirmed_by=admin_id)
        if not ok:
            await callback.answer("ℹ️ Не удалось подтвердить оплату (возможно уже подтверждена).", show_alert=True)
            # Попробуем обновить карточку корректным текстом
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order:
                new_text, new_kb = build_order_dashboard_payload(order)  # см. функция ниже
                await safe_refresh_dashboard(bot=callback.bot, message=callback.message, new_text=new_text, new_kb=new_kb)
            return

        # 2) Логируем действие
        try:
            await db_manager.add_user_action(user_id=admin_id, action_type='payment_confirmed', action_data={'order_id': order_id})
        except Exception:
            logger.debug("add_user_action failed (non-critical)")

        # 3) Уведомляем клиента
        try:
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order and order.get('user_id'):
                await bot.send_message(order['user_id'], f"✅ Оплата по заказу #{order_id} подтверждена. Спасибо — заказ принят в работу.")
        except Exception as e:
            logger.debug(f"Failed to notify customer about confirmed payment #{order_id}: {e}")

        # 4) Ответ админу и обновление карточки: оставляем только кнопку "В приготовление"
        await callback.answer("✅ Оплата подтверждена", show_alert=False)

        # Формируем короткий текст + клавиатуру с одной кнопкой
        order = await db_manager.get_delivery_order_by_id(order_id)
        if not order:
            # если вдруг не нашли — fallback: просто удаляем кнопку
            try:
                await callback.message.edit_reply_markup(None)
            except Exception:
                pass
            return

        # Короткий текст (можно адаптировать под ваш стиль)
        new_text = (
            f"🆕 <b>Заказ #{order_id}</b>\n\n"
            f"👤 {order.get('customer_name')}\n"
            f"📞 {order.get('customer_phone')}\n"
            f"🏠 {order.get('delivery_address')}\n\n"
            f"💰 Сумма: {order.get('final_amount')}₽\n"
            f"📌 Статус: <b>{order.get('status') or 'pending'}</b>\n"
            f"💳 Оплата: <b>{order.get('payment_method')} ({order.get('payment_status')})</b>\n\n"
            f"<i>Оплата подтверждена — ожидается начало приготовления</i>"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="👨‍🍳 В приготовление", callback_data=f"dashboard_start_{order_id}")
        kb.adjust(1)

        # Обновляем админское сообщение безопасно
        await safe_refresh_dashboard(bot=callback.bot, message=callback.message, new_text=new_text, new_kb=kb)

    except Exception as e:
        logger.exception(f"Error in admin_handle_payment_confirm: {e}")
        try:
            await callback.answer("❌ Внутренняя ошибка, смотри логи.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("payment_reject_"))
async def admin_handle_payment_reject(callback: CallbackQuery, db_manager: DatabaseManager, bot: Bot):
    """Админ отклонил оплату (кнопка '❌ Отклонить оплату' на квитанции)."""
    try:
        admin_id = callback.from_user.id
        # Проверка прав
        admin_ids = [int(a.strip()) for a in settings.ADMIN_IDS.split(",") if a.strip()]
        if admin_id not in admin_ids:
            await callback.answer("❌ У вас нет прав для этого действия.", show_alert=True)
            return

        # Разбор order_id
        try:
            order_id = int(callback.data.split("payment_reject_")[-1])
        except Exception:
            await callback.answer("❌ Неверный формат callback.", show_alert=True)
            logger.warning(f"Bad callback data for payment_reject: {callback.data}")
            return

        # Отклоняем оплату (атомарно) — предполагается, что это ставит payment_status = 'rejected'
        ok = await db_manager.reject_payment(order_id, rejected_by=admin_id)
        if not ok:
            await callback.answer("ℹ️ Не удалось отклонить оплату (возможно уже отклонена).", show_alert=True)
            try:
                order = await db_manager.get_delivery_order_by_id(order_id)
                if order:
                    # Попробуем обновить карточку в админском сообщении
                    new_text, new_kb = build_order_dashboard_payload(order)
                    await safe_refresh_dashboard(bot=callback.bot, message=callback.message, new_text=new_text, new_kb=new_kb)
            except Exception:
                logger.debug("Failed to refresh dashboard after failed reject (non-critical)")
            return

        # Лог действия
        try:
            await db_manager.add_user_action(user_id=admin_id, action_type='payment_rejected', action_data={'order_id': order_id})
        except Exception:
            logger.debug("add_user_action failed (non-critical)")

        # Нотификация клиента
        try:
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order and order.get('user_id'):
                await bot.send_message(
                    order['user_id'],
                    f"❌ Оплата по заказу #{order_id} отклонена. Пожалуйста, пришлите корректный скрин или свяжитесь с нами."
                )
        except Exception as e:
            logger.debug(f"Failed to notify customer about rejected payment #{order_id}: {e}")

        # Попробуем изменить статус заказа на 'cancelled' если он всё ещё в 'pending'
        try:
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order:
                current_status = (order.get('status') or '').lower()
                if current_status == 'pending':
                    try:
                        await db_manager.update_delivery_order_status(order_id, "cancelled")
                        logger.info(f"Order #{order_id} status set to 'cancelled' after payment rejected")
                    except Exception as e:
                        logger.exception(f"Failed to set order #{order_id} to 'cancelled': {e}")
                else:
                    logger.info(f"Order #{order_id} not cancelled after payment reject (current status: {current_status})")
        except Exception as e:
            logger.exception(f"Failed to fetch order #{order_id} after reject: {e}")

        await callback.answer("❌ Оплата отклонена", show_alert=False)

        # Обновляем сообщение админа через безопасную функцию (показать, что оплата отклонена).
        try:
            # Подгрузим актуальный order ещё раз (чтобы показать обновлённый статус)
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order:
                new_text = (
                    f"❌ <b>ОПЛАТА ОТКЛОНЕНА</b>\n\n"
                    f"🆕 Заказ #{order_id}\n\n"
                    f"👤 {order.get('customer_name', '—')}\n"
                    f"📞 {order.get('customer_phone', '—')}\n"
                    f"🏠 {order.get('delivery_address', '—')}\n\n"
                    f"💰 Сумма: {order.get('final_amount') or order.get('total_amount', 0)}₽\n"
                    f"📌 Статус: <b>{order.get('status') or '—'}</b>\n"
                    f"💳 Оплата: <b>{order.get('payment_method') or '—'} (rejected)</b>\n\n"
                    f"<i>Админ отклонил оплату. Клиенту отправлено уведомление.</i>"
                )

                from aiogram.utils.keyboard import InlineKeyboardBuilder
                kb = InlineKeyboardBuilder()
                kb.button(text="🔁 Обновить панель", callback_data="dashboard_refresh")
                kb.adjust(1)

                await safe_refresh_dashboard(
                    bot=callback.bot,
                    message=callback.message,
                    new_text=new_text,
                    new_kb=kb
                )
            else:
                # Если по какой-то причине order не найден — просто уберём клавиатуру и покажем уведомление
                try:
                    await callback.message.edit_reply_markup(None)
                except Exception:
                    logger.debug("Could not clear reply_markup on callback.message")
        except Exception as e:
            logger.exception(f"Failed to refresh admin message after rejecting payment #{order_id}: {e}")

        # Обновляем общую панель управления (чтобы заказ исчез/обновился в списках)
        try:
            await refresh_dashboard(callback.message, db_manager)
        except Exception as e:
            logger.debug(f"Failed to refresh main dashboard after payment reject: {e}")

    except Exception as e:
        logger.exception(f"Error in admin_handle_payment_reject: {e}")
        try:
            await callback.answer("❌ Внутренняя ошибка, смотри логи.", show_alert=True)
        except Exception:
            pass



def build_order_dashboard_payload(order: dict):
    """
    Возвращает (text, inline_kb) для админского сообщения по order dict.
    Подстраивается под текущий статус и payment_status.
    """
    order_id = order.get('id')
    customer = order.get('customer_name') or '—'
    phone = order.get('customer_phone') or '—'
    addr = order.get('delivery_address') or '—'
    total = order.get('final_amount') or order.get('total_amount') or 0
    status = order.get('status') or 'pending'
    payment_method = order.get('payment_method') or order.get('order_data', {}).get('payment_method')
    payment_status = order.get('payment_status') or 'pending'

    # Формируем текст
    items_text = ""
    try:
        items = order.get('order_data', {}).get('items', [])
        if items:
            items_text = "<b>Состав заказа:</b>\n"
            for it in items:
                name = it.get('name', '—')
                qty = it.get('quantity', 1)
                price = it.get('price', 0)
                line_sum = (float(price) * int(qty)) if price is not None else 0
                items_text += f"• {name} x{qty} — {int(line_sum)}₽\n"
            items_text += "\n"
    except Exception:
        items_text = ""

    text = (
        f"🆕 <b>Заказ #{order_id}</b>\n\n"
        f"👤 {customer}\n"
        f"📞 {phone}\n"
        f"🏠 {addr}\n\n"
        f"💰 Сумма: {total}₽\n"
        f"📌 Статус: <b>{status}</b>\n"
        f"💳 Оплата: <b>{payment_method} ({payment_status})</b>\n\n"
        f"{items_text}"
    )

    # Формируем клавиатуру
    kb = InlineKeyboardBuilder()
    # Payment buttons: только если ожидается подтверждение
    if str(payment_status).lower() == 'pending' and str(payment_method) in ('card', 'bank_transfer'):
        kb.button(text="✅ Подтвердить оплату", callback_data=f"payment_confirm_{order_id}")
        kb.button(text="❌ Отклонить оплату", callback_data=f"payment_reject_{order_id}")

    # Стандартные кнопки управления заказом
    kb.button(text="👨‍🍳 В приготовление", callback_data=f"dashboard_start_{order_id}")
    kb.button(text="🚗 Передать курьеру", callback_data=f"dashboard_ship_{order_id}")
    kb.button(text="✅ Доставлен", callback_data=f"dashboard_delivered_{order_id}")
    kb.button(text="📞 Позвонить", callback_data=f"dashboard_call_{order_id}")
    kb.adjust(2)

    return text, kb



@router.callback_query(F.data.startswith("dashboard_start_"))
async def start_preparing_order(callback: CallbackQuery, db_manager: DatabaseManager):
    """Начать приготовление заказа (теперь с безопасной обработкой фото-сообщений)."""
    try:
        order_id = int(callback.data.split("_")[2])

        # Обновляем статус
        success = await db_manager.update_delivery_order_status(order_id, "preparing")
        if success:
            await callback.answer("👨‍🍳 Заказ взят в приготовление")

            # Получаем заказ
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order:
                dashboard = DeliveryDashboard(db_manager)
                updated_text = await dashboard.format_order_card(order, urgent=False)
                updated_text = f"👨‍🍳 <b>В ПРИГОТОВЛЕНИИ</b>\n\n{updated_text}"

                from aiogram.utils.keyboard import InlineKeyboardBuilder
                keyboard = InlineKeyboardBuilder()
                keyboard.button(text="🚗 В путь", callback_data=f"dashboard_ship_{order_id}")
                keyboard.button(text="📞 Позвонить", callback_data=f"dashboard_call_{order_id}")
                keyboard.adjust(2)

                # Унифицированное безопасное обновление админского сообщения
                try:
                    await safe_refresh_dashboard(
                        bot=callback.bot,
                        message=callback.message,
                        new_text=updated_text,
                        new_kb=keyboard
                    )
                except Exception as e:
                    logger.exception(f"Failed to refresh admin message on start_preparing_order: {e}")
                    # fallback: отправим отдельное сообщение админу
                    try:
                        await callback.message.answer(updated_text, parse_mode="HTML", reply_markup=keyboard.as_markup())
                    except Exception as send_e:
                        logger.debug(f"Fallback send failed: {send_e}")

            # Обновляем дашборд
            await refresh_dashboard(callback.message, db_manager)

        else:
            await callback.answer("❌ Ошибка при обновлении статуса")

    except Exception as e:
        logger.error(f"❌ Error starting order preparation: {e}")
        await callback.answer("❌ Ошибка при обновлении заказа")


@router.callback_query(F.data.startswith("dashboard_ship_"))
async def ship_order(callback: CallbackQuery, db_manager: DatabaseManager):
    """Передать заказ курьеру"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        success = await db_manager.update_delivery_order_status(order_id, "on_way")
        if success:
            await callback.answer("🚗 Заказ передан курьеру")
            
            # Обновляем сообщение
            order = await db_manager.get_delivery_order_by_id(order_id)
            if order:
                dashboard = DeliveryDashboard(db_manager)
                updated_text = await dashboard.format_order_card(order, urgent=False)
                updated_text = f"🚗 <b>В ПУТИ</b>\n\n{updated_text}"
                
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                keyboard = InlineKeyboardBuilder()
                keyboard.button(text="✅ Доставлен", callback_data=f"dashboard_delivered_{order_id}")
                keyboard.button(text="📞 Позвонить", callback_data=f"dashboard_call_{order_id}")
                
                # Унифицированное безопасное обновление админского сообщения
                try:
                    await safe_refresh_dashboard(
                        bot=callback.bot,
                        message=callback.message,
                        new_text=updated_text,
                        new_kb=keyboard
                    )
                except Exception as e:
                    logger.exception(f"Failed to refresh admin message on ship_order: {e}")
                    # fallback: попробуем редактировать текст как раньше
                    try:
                        await callback.message.edit_text(updated_text, parse_mode="HTML", reply_markup=keyboard.as_markup())
                    except Exception as edit_error:
                        if "message is not modified" not in str(edit_error):
                            logger.exception(f"ship_order: fallback edit_text failed: {edit_error}")
            
            await refresh_dashboard(callback.message, db_manager)
        else:
            await callback.answer("❌ Ошибка при обновлении статуса")
            
    except Exception as e:
        logger.error(f"❌ Error shipping order: {e}")
        await callback.answer("❌ Ошибка при обновлении заказа")

@router.callback_query(F.data.startswith("dashboard_delivered_"))
async def mark_order_delivered(callback: CallbackQuery, db_manager: DatabaseManager):
    """Отметить заказ как доставленный - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        # СНАЧАЛА получаем информацию о заказе
        order = await db_manager.get_delivery_order_by_id(order_id)
        if not order:
            await callback.answer("❌ Заказ не найден")
            return
        
        user_id = order['user_id']
        
        # Проверяем, не доставлен ли заказ уже
        if order['status'] == 'delivered':
            await callback.answer("❌ Заказ уже доставлен")
            return
        
        # ОБНОВЛЯЕМ статус заказа
        success = await db_manager.update_delivery_order_status(order_id, "delivered")
        
        if success:
            # ПРОВЕРЯЕМ и НАЧИСЛЯЕМ реферальный бонус
            user = await db_manager.get_user(user_id)
            if user and user.get('referrer_id'):
                # Проверяем, это первый ДОСТАВЛЕННЫЙ заказ пользователя
                user_orders = await db_manager.get_delivery_orders_by_user(user_id)
                delivered_orders = [o for o in user_orders if o['status'] == 'delivered']
                
                if len(delivered_orders) == 1:  # Это первый доставленный заказ
                    bonus_success = await db_manager.complete_referral_bonus(user_id, order_id)
                    if bonus_success:
                        logger.info(f"✅ Referral bonus awarded for order {order_id}, user {user_id}")
                    else:
                        logger.warning(f"⚠️ Failed to award referral bonus for order {order_id}")
            
            await callback.answer("✅ Заказ доставлен")
            await refresh_dashboard(callback.message, db_manager)
        else:
            await callback.answer("❌ Ошибка при обновлении статуса")
            
    except Exception as e:
        logger.error(f"❌ Error marking order delivered: {e}")
        await callback.answer("❌ Ошибка при обновлении заказа")

@router.callback_query(F.data.startswith("dashboard_call_"))
async def show_customer_phone(callback: CallbackQuery, db_manager: DatabaseManager):
    """Показать номер телефона клиента"""
    try:
        order_id = int(callback.data.split("_")[2])
        
        order = await db_manager.get_delivery_order_by_id(order_id)
        if order:
            await callback.answer(f"📞 Телефон: +{order['customer_phone']}", show_alert=True)
        else:
            await callback.answer("❌ Заказ не найден")
            
    except Exception as e:
        logger.error(f"❌ Error getting customer phone: {e}")
        await callback.answer("❌ Ошибка при получении данных")