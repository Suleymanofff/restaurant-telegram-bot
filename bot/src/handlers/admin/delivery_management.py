# from aiogram import Router, F, Bot
# from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, ReplyKeyboardRemove
# from aiogram.utils.keyboard import InlineKeyboardBuilder
# from fluent.runtime import FluentLocalization
# import logging
# import json

# from src.handlers.admin.delivery_dashboard import DeliveryDashboard
# from src.database.db_manager import DatabaseManager
# from src.utils.config import settings

# router = Router()
# logger = logging.getLogger(__name__)

# @router.message(F.text == "📦 Управление доставкой__")
# async def show_delivery_orders_menu(message: Message, db_manager: DatabaseManager, l10n: FluentLocalization):
#     """Меню управления заказами доставки для АДМИНОВ"""
#     if not settings.is_admin(message.from_user.id):
#         await message.answer("❌ У вас нет прав для управления заказами")
#         return
    
#     builder = InlineKeyboardBuilder()
#     builder.row(
#         InlineKeyboardButton(text="⏳ Ожидающие", callback_data="admin_pending_delivery"),
#         InlineKeyboardButton(text="👨‍🍳 В приготовлении", callback_data="admin_preparing_delivery")
#     )
#     builder.row(
#         InlineKeyboardButton(text="🚗 В пути", callback_data="admin_onway_delivery"),
#         InlineKeyboardButton(text="✅ Доставленные", callback_data="admin_delivered_delivery")
#     )
    
#     await message.answer(
#         "📦 Панель управления заказами доставки:",
#         reply_markup=builder.as_markup()
#     )

# @router.callback_query(F.data.startswith("admin_"))
# async def show_delivery_orders(callback: CallbackQuery, db_manager: DatabaseManager, l10n: FluentLocalization):
#     """Показ заказов доставки по статусу"""
#     status_map = {
#         "admin_pending_delivery": "pending",
#         "admin_preparing_delivery": "preparing", 
#         "admin_onway_delivery": "on_way",
#         "admin_delivered_delivery": "delivered"
#     }
    
#     status = status_map.get(callback.data)
#     if not status:
#         await callback.answer("❌ Неизвестный статус")
#         return
    
#     orders = await db_manager.get_delivery_orders_by_status(status)
    
#     if not orders:
#         await callback.message.edit_text(f"📭 Нет заказов со статусом: {status}")
#         return
    
#     for order in orders[:3]:  # Показываем первые 3 заказа
#         order_text = format_delivery_order_text(order)
        
#         builder = InlineKeyboardBuilder()
#         if status == "pending":
#             builder.row(
#                 InlineKeyboardButton(text="👨‍🍳 В приготовление", callback_data=f"delivery_preparing_{order['id']}"),
#             )
#         elif status == "preparing":
#             builder.row(
#                 InlineKeyboardButton(text="🚗 В путь", callback_data=f"delivery_onway_{order['id']}"),
#             )
#         elif status == "on_way":
#             builder.row(
#                 InlineKeyboardButton(text="✅ Доставлен", callback_data=f"delivery_delivered_{order['id']}"),
#             )
        
#         await callback.message.answer(order_text, reply_markup=builder.as_markup())
    
#     await callback.answer()

# @router.callback_query(F.data.startswith("delivery_"))
# async def update_delivery_order_status(callback: CallbackQuery, db_manager: DatabaseManager, l10n: FluentLocalization, bot: Bot):
#     """Обновление статуса заказа доставки"""
#     try:
#         action, order_id = callback.data.split("_")[1], int(callback.data.split("_")[2])
        
#         status_map = {
#             "preparing": "preparing",
#             "onway": "on_way", 
#             "delivered": "delivered"
#         }
        
#         new_status = status_map.get(action)
#         if not new_status:
#             await callback.answer("❌ Неизвестное действие")
#             return
        
#         success = await db_manager.update_delivery_order_status(order_id, new_status)
        
#         if success:
#             # Получаем обновленный заказ
#             orders = await db_manager.get_delivery_orders_by_status(new_status)
#             updated_order = next((o for o in orders if o['id'] == order_id), None)
            
#             if updated_order:
#                 # Уведомляем пользователя
#                 await notify_user_about_delivery_status(bot, updated_order)
                
#                 # Обновляем сообщение у админа
#                 updated_text = format_delivery_order_text(updated_order)
#                 await callback.message.edit_text(
#                     updated_text,
#                     reply_markup=None
#                 )
                
#             await callback.answer(f"✅ Статус заказа обновлен на: {new_status}")
#         else:
#             await callback.answer("❌ Ошибка при обновлении статуса")
        
#     except Exception as e:
#         logger.error(f"❌ Error updating delivery order: {e}")
#         await callback.answer("❌ Ошибка при обновлении заказа")

# def format_delivery_order_text(order: dict) -> str:
#     """Форматирование текста заказа доставки"""
#     # Преобразуем order_data из JSON строки в словарь
#     try:
#         if isinstance(order['order_data'], str):
#             order_data = json.loads(order['order_data'])
#         else:
#             order_data = order['order_data']
#     except (json.JSONDecodeError, KeyError, TypeError):
#         order_data = {}
    
#     text = f"🛵 <b>ЗАКАЗ ДОСТАВКИ #{order['id']}</b>\n\n"
    
#     text += "<b>Состав заказа:</b>\n"
#     items = order_data.get('items', [])
    
#     if not items:
#         text += "• Состав заказа не указан\n"
#     else:
#         for item in items:
#             text += f"• {item.get('name', 'Unknown')} x{item.get('quantity', 1)}\n"
    
#     text += f"\n💰 <b>Сумма: {order['total_amount']}₽</b>\n\n"
    
#     text += "<b>Данные клиента:</b>\n"
#     text += f"👤 Имя: {order['customer_name']}\n"
#     text += f"📞 Телефон: {order['customer_phone']}\n"
#     text += f"🏠 Адрес: {order['delivery_address']}\n"
#     text += f"🕐 Время: {order.get('delivery_time', 'Как можно скорее')}\n\n"
    
#     text += f"📊 <b>Статус:</b> {order['status']}\n"
#     text += f"⏰ Создан: {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
    
#     return text

# async def notify_user_about_delivery_status(bot: Bot, order: dict):
#     """Уведомление пользователя об изменении статуса заказа"""
#     try:
#         status_messages = {
#             "preparing": "👨‍🍳 Ваш заказ начали готовить!",
#             "on_way": "🚗 Ваш заказ в пути! Курьер уже едет к вам.",
#             "delivered": "✅ Ваш заказ доставлен! Приятного аппетита!"
#         }
        
#         message = status_messages.get(order['status'])
#         if message and order['user_id']:
#             await bot.send_message(
#                 order['user_id'],
#                 f"{message}\n\nЗаказ #{order['id']}"
#             )
#     except Exception as e:
#         logger.error(f"❌ Failed to notify user about delivery status: {e}")