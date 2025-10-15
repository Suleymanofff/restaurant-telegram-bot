from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluent.runtime import FluentLocalization
import logging
from datetime import datetime

from src.database.db_manager import DatabaseManager
from src.utils.logger import get_logger

router = Router()
logger = get_logger(__name__)

class LoyaltyCardManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    async def get_loyalty_card_info(self, user_id: int) -> dict:
        """Получение всей информации для карты лояльности"""
        try:
            user = await self.db_manager.get_user(user_id)
            bonus_balance = user.get('bonus_balance', 0) if user else 0
            transactions = await self.db_manager.get_bonus_transactions(user_id, limit=5)
            
            # Статистика по транзакциям
            earned = sum(t['amount'] for t in transactions if t['amount'] > 0)
            spent = abs(sum(t['amount'] for t in transactions if t['amount'] < 0))
            
            return {
                'balance': bonus_balance,
                'transactions': transactions,
                'stats': {
                    'earned': earned,
                    'spent': spent,
                    'total_orders': len([t for t in transactions if t['type'] == 'cashback'])
                }
            }
        except Exception as e:
            logger.error(f"❌ Error getting loyalty card info: {e}")
            return {'balance': 0, 'transactions': [], 'stats': {'earned': 0, 'spent': 0, 'total_orders': 0}}

@router.message(F.text == "💳 Карта лояльности")
async def loyalty_program_handler(message: Message, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Обработчик кнопки 'Карта лояльности'"""
    try:
        user_id = message.from_user.id
        
        # 🔥 ГАРАНТИРУЕМ, ЧТО ПОЛЬЗОВАТЕЛЬ СУЩЕСТВУЕТ В БАЗЕ
        await db_manager.ensure_user_exists(
            user_id=user_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        
        loyalty_manager = LoyaltyCardManager(db_manager)
        card_info = await loyalty_manager.get_loyalty_card_info(user_id)
        
        # Форматируем сообщение
        text = await format_loyalty_card_message(card_info, db_manager)
        
        # Создаем клавиатуру
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text="📊 История операций", 
            callback_data="bonus_history"
        )
        
        builder.button(
            text="ℹ️ Правила программы", 
            callback_data="bonus_rules"
        )
        
        builder.button(
            text="🔄 Обновить", 
            callback_data="refresh_bonus"
        )
        
        builder.adjust(1)
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
        # Логируем действие
        await db_manager.add_user_action(
            user_id=user_id,
            action_type='loyalty_program_click'
        )
        
        logger.info(f"💳 Loyalty card shown to user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error in loyalty_program_handler: {e}")
        await message.answer("❌ Произошла ошибка при загрузке информации о бонусной программе.")

async def format_loyalty_card_message(card_info: dict, db_manager=None) -> str:
    """Форматирование сообщения карты лояльности с улучшенным отображением рефералов"""
    balance = card_info['balance']
    stats = card_info['stats']
    transactions = card_info['transactions']
    
    text = "💳 <b>ВАША КАРТА ЛОЯЛЬНОСТИ</b>\n\n"
    
    # Баланс
    text += f"💰 <b>Текущий баланс:</b> <code>{balance}₽</code>\n\n"
    
    # Статистика
    text += "📊 <b>Ваша статистика:</b>\n"
    text += f"• Всего заработано: {stats['earned']}₽\n"
    text += f"• Использовано: {stats['spent']}₽\n"
    text += f"• Заказов с кешбэком: {stats['total_orders']}\n\n"
    
    # Последние операции
    if transactions:
        text += "🕐 <b>Последние операции:</b>\n"
        for transaction in transactions[:3]:  # Показываем 3 последние
            emoji = "⬆️" if transaction['amount'] > 0 else "⬇️"
            sign = "+" if transaction['amount'] > 0 else ""
            date = transaction['created_at'].strftime("%d.%m %H:%M")
            
            # Улучшаем описание для реферальных бонусов
            description = transaction['description']
            
            # Если это реферальный бонус и есть доступ к db_manager
            if 'реферальный бонус за пользователя' in description.lower() and db_manager:
                try:
                    # Извлекаем user_id из описания
                    import re
                    user_id_match = re.search(r'(\d+)', description)
                    if user_id_match:
                        referred_user_id = int(user_id_match.group(1))
                        # Получаем информацию о пользователе
                        referred_user = await db_manager.get_user(referred_user_id)
                        if referred_user:
                            # Используем username или full_name
                            if referred_user.get('username'):
                                user_display = f"@{referred_user['username']}"
                            else:
                                user_display = referred_user.get('full_name', 'пользователь')
                            
                            # Обновляем описание
                            description = f"Реферальный бонус за {user_display}"
                except Exception as e:
                    # В случае ошибки оставляем оригинальное описание
                    print(f"❌ Error formatting referral description: {e}")
            
            text += f"{emoji} {sign}{transaction['amount']}₽ - {description}\n"
            text += f"   <i>{date}</i>\n\n"
    else:
        text += "📝 <i>У вас пока нет операций по бонусному счету</i>\n\n"
    
    # Правила программы
    text += "🎯 <b>Правила программы:</b>\n"
    text += "• <b>5% кешбэк</b> от каждого заказа\n"
    text += "• Можно оплатить <b>до 50%</b> суммы заказа бонусами\n"
    text += "• Минимальная сумма заказа для бонусов: <b>500₽</b>\n"
    text += "• Бонусы <b>не сгорают</b>\n\n"
    
    text += "💡 <i>Бонусы автоматически начисляются после доставки заказа и применяются при следующем заказе</i>"
    
    return text

@router.callback_query(F.data == "bonus_history")
async def show_bonus_history(callback: CallbackQuery, db_manager: DatabaseManager):
    """Показать полную историю бонусов"""
    try:
        user_id = callback.from_user.id
        transactions = await db_manager.get_bonus_transactions(user_id, limit=20)

        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад к карте", callback_data="back_to_loyalty_card")
        
        if not transactions:
            await callback.message.edit_text(
                "📝 <b>История операций</b>\n\nУ вас пока нет операций по бонусному счету.",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
            return
        
        text = "📊 <b>ПОЛНАЯ ИСТОРИЯ ОПЕРАЦИЙ</b>\n\n"
        
        for transaction in transactions:
            emoji = "🟢" if transaction['amount'] > 0 else "🔴"
            sign = "+" if transaction['amount'] > 0 else ""
            date = transaction['created_at'].strftime("%d.%m.%Y %H:%M")
            
            text += f"{emoji} <b>{date}</b>\n"
            text += f"   {transaction['description']}\n"
            text += f"   Сумма: <code>{sign}{transaction['amount']}₽</code>\n\n"
        
        
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in show_bonus_history: {e}")
        await callback.answer("❌ Ошибка при загрузке истории", show_alert=True)

@router.callback_query(F.data == "bonus_rules")
async def show_bonus_rules(callback: CallbackQuery):
    """Показать правила бонусной программы"""
    try:
        text = (
            "📋 <b>ПРАВИЛА БОНУСНОЙ ПРОГРАММЫ</b>\n\n"
            
            "💎 <b>Начисление бонусов:</b>\n"
            "• <b>5% кешбэк</b> от суммы каждого доставленного заказа\n"
            "• Бонусы начисляются после подтверждения доставки\n"
            "• Дополнительные бонусы в акциях и специальных предложениях\n\n"
            
            "💰 <b>Использование бонусов:</b>\n"
            "• Можно оплатить <b>до 50%</b> стоимости заказа\n"
            "• Минимальная сумма заказа для использования: <b>500₽</b>\n"
            "• Бонусы применяются автоматически при оформлении\n"
            "• Нельзя вывести наличными или передать другому лицу\n\n"
            
            "⏰ <b>Сроки действия:</b>\n"
            "• Бонусы не сгорают\n"
            "• Начисляются после подтверждения заказа\n"
            "• Доступны для использования сразу после начисления\n\n"
            
            "🎁 <b>Дополнительные возможности:</b>\n"
            "• Участие в специальных акциях\n"
            "• Персональные предложения\n"
            "• Приоритетная доставка для активных пользователей\n\n"
            
            "❓ <b>Вопросы и поддержка:</b>\n"
            "По всем вопросам обращайтесь к администратору"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Назад к карте", callback_data="back_to_loyalty_card")
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in show_bonus_rules: {e}")
        await callback.answer("❌ Ошибка при загрузке правил", show_alert=True)

@router.callback_query(F.data == "refresh_bonus")
async def refresh_bonus_info(callback: CallbackQuery, db_manager: DatabaseManager):
    """Обновить информацию о бонусах"""
    try:
        user_id = callback.from_user.id
        loyalty_manager = LoyaltyCardManager(db_manager)
        card_info = await loyalty_manager.get_loyalty_card_info(user_id)
        
        text = await format_loyalty_card_message(card_info)
        
        # Восстанавливаем клавиатуру
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 История операций", callback_data="bonus_history")
        builder.button(text="ℹ️ Правила программы", callback_data="bonus_rules")
        builder.button(text="🔄 Обновить", callback_data="refresh_bonus")
        builder.adjust(1)
        
        try:
            await callback.message.edit_text(
                text, 
                parse_mode="HTML", 
                reply_markup=builder.as_markup()
            )
            await callback.answer("✅ Информация обновлена")
        except Exception as edit_error:
            if "message is not modified" in str(edit_error):
                # Сообщение не изменилось - это нормально
                await callback.answer("✅ Информация актуальна")
            else:
                # Другая ошибка - пробрасываем дальше
                raise edit_error
        
    except Exception as e:
        logger.error(f"❌ Error in refresh_bonus_info: {e}")
        await callback.answer("❌ Ошибка при обновлении", show_alert=True)

@router.callback_query(F.data == "back_to_loyalty_card")
async def back_to_loyalty_card(callback: CallbackQuery, db_manager: DatabaseManager):
    """Возврат к основной карте лояльности"""
    try:
        user_id = callback.from_user.id
        loyalty_manager = LoyaltyCardManager(db_manager)
        card_info = await loyalty_manager.get_loyalty_card_info(user_id)
        
        text = await format_loyalty_card_message(card_info)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 История операций", callback_data="bonus_history")
        builder.button(text="ℹ️ Правила программы", callback_data="bonus_rules")
        builder.button(text="🔄 Обновить", callback_data="refresh_bonus")
        builder.adjust(1)
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in back_to_loyalty_card: {e}")
        await callback.answer("❌ Ошибка при возврате", show_alert=True)