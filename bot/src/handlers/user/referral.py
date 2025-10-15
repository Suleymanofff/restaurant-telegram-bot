from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluent.runtime import FluentLocalization
import logging

from src.database.db_manager import DatabaseManager
from src.utils.logger import get_logger
from src.utils.config import settings

router = Router()
logger = get_logger(__name__)

async def process_referral_activation(user_id: int, referral_code: str, db_manager: DatabaseManager, bot, source: str) -> bool:
    """УНИФИЦИРОВАННАЯ функция активации реферального кода"""
    try:
        # Нормализуем код
        referral_code = referral_code.upper().strip()
        
        logger.info(f"🔍 Processing referral activation: user {user_id}, code {referral_code}, source {source}")
        
        # Проверяем свой ли код
        user_referral_code = await db_manager.get_referral_code(user_id)
        if referral_code == user_referral_code:
            logger.warning(f"⚠️ User {user_id} tried to use own referral code")
            return False
        
        # Получаем информацию о пользователе с проверкой реферера
        current_user = await db_manager.get_user(user_id)
        if current_user and current_user.get('referrer_id'):
            logger.warning(f"⚠️ User {user_id} already has referrer: {current_user.get('referrer_id')}")
            return False
        
        # Ищем реферера
        referrer = await db_manager.get_user_by_referral_code(referral_code)
        if not referrer:
            logger.warning(f"⚠️ Referral code not found: {referral_code}")
            return False
        
        # Проверяем самоссылку
        if referrer['user_id'] == user_id:
            logger.warning(f"⚠️ Self-referral attempt: {user_id}")
            return False
        
        # АТОМАРНАЯ установка реферера
        success = await db_manager.set_user_referrer(user_id, referrer['user_id'])
        if not success:
            logger.error(f"❌ Failed to set referrer for user {user_id}")
            return False
        
        # Создаем бонус ТОЛЬКО если реферер успешно установлен
        bonus_created = await db_manager.add_referral_bonus(
            referrer_id=referrer['user_id'],
            referred_id=user_id,
            bonus_amount=200.00
        )
        
        if not bonus_created:
            logger.error(f"❌ Failed to create referral bonus for {user_id}")
            # В этом случае реферер установлен, но бонус не создан - это нормально, он создастся позже
        
        # Уведомляем реферера
        try:
            user_info = await bot.get_chat(user_id)
            user_name = user_info.full_name
            username = f"@{user_info.username}" if user_info.username else "не указан"
            
            referrer_notification = (
                f"🎉 <b>У вас новый реферал!</b>\n\n"
                f"👤 Пользователь: {user_name}\n"
                f"📞 Username: {username}\n"
                f"📱 Источник: {source}\n\n"
                f"💰 Вы получите <b>200₽</b> после его первого заказа!\n"
                f"💳 Следите за статусом в разделе '💳 Карта лояльности'"
            )
            await bot.send_message(
                chat_id=referrer['user_id'],
                text=referrer_notification,
                parse_mode="HTML"
            )
            logger.info(f"✅ Notified referrer {referrer['user_id']} about new referral")
        except Exception as notify_error:
            logger.error(f"❌ Failed to notify referrer: {notify_error}")
        
        logger.info(f"✅ Referral activated: user {user_id} -> referrer {referrer['user_id']} (source: {source})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in process_referral_activation: {e}", exc_info=True)
        return False

@router.message(F.text == "👥 Пригласи друга")
async def invite_friend_handler(message: Message, l10n: FluentLocalization, db_manager: DatabaseManager):
    """Главное меню реферальной программы"""
    try:
        user_id = message.from_user.id
        
        # Получаем реферальный код пользователя
        referral_code = await db_manager.get_referral_code(user_id)
        
        # Получаем статистику рефералов
        referral_stats = await db_manager.get_referral_stats(user_id)
        
        text = (
            f"👥 <b>ПРИГЛАСИ ДРУГА - ПОЛУЧИ 200₽</b>\n\n"
            
            f"💎 <b>Как это работает:</b>\n"
            f"• Даешь другу свой код\n"
            f"• Друг делает первый заказ от 500₽\n"
            f"• Ты получаешь <b>200₽</b> на счет\n"
            f"• Друг получает <b>10% скидку</b> на первый заказ\n\n"
            
            f"📊 <b>Твоя статистика:</b>\n"
            f"• Приглашено друзей: {referral_stats['total_referrals']}\n"
            f"• Успешных приглашений: {referral_stats['completed_referrals']}\n"
            f"• Заработано бонусов: {referral_stats['total_referral_bonus']}₽\n"
            f"• Ожидают заказа: {referral_stats['pending_referrals']}\n\n"
            
            f"🎯 <b>Твой реферальный код:</b>\n"
            f"<code>{referral_code}</code>\n\n"
            
            f"💡 <b>Как делиться кодом:</b>\n"
            f"1. Отправь другу свой код\n"
            f"2. Друг должен ввести его при первом заказе\n"
            f"3. Или перешли готовое сообщение ниже\n"
        )
        
        # Создаем инлайн-клавиатуру
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text="📤 Поделиться кодом", 
            callback_data="share_referral"
        )
        
        builder.button(
            text="📋 Правила программы", 
            callback_data="referral_rules"
        )
        
        builder.button(
            text="🔄 Обновить статистику", 
            callback_data="refresh_referral_stats"
        )
        
        builder.adjust(1)
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
        # Отправляем готовое сообщение для пересылки
        share_text = (
            f"🍽️ <b>Привет! У меня есть для тебя подарок!</b>\n\n"
            f"Дарим тебе <b>10% скидку</b> на первый заказ в нашем ресторане! 🎁\n\n"
            f"💎 Просто используй мой реферальный код при заказе:\n"
            f"<code>{referral_code}</code>\n\n"
            f"🛵 Заказывай доставку или бронируй стол - скидка действует везде!\n"
            f"А я получу бонус за твой первый заказ 😊\n\n"
            f"📍 Наш ресторан: {settings.RESTAURANT_ADDRESS}"
        )
        
        await message.answer(
            "📤 <b>Готовое сообщение для пересылки:</b>\n\n"
            "Просто скопируй и отправь другу 👇",
            parse_mode="HTML"
        )
        
        await message.answer(share_text, parse_mode="HTML")
        
        # Логируем действие
        await db_manager.add_user_action(
            user_id=user_id,
            action_type='referral_program_click'
        )
        
        logger.info(f"👥 Referral program shown to user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error in invite_friend_handler: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке реферальной программы.")

@router.callback_query(F.data == "share_referral")
async def share_referral_code(callback: CallbackQuery, db_manager: DatabaseManager):
    """Поделиться реферальным кодом"""
    try:
        user_id = callback.from_user.id
        referral_code = await db_manager.get_referral_code(user_id)
        
        share_text = (
            f"🍽️ <b>Дарим тебе 10% скидку на первый заказ!</b>\n\n"
            f"Используй мой реферальный код:\n"
            f"<code>{referral_code}</code>\n\n"
            f"🎁 <b>Что ты получаешь:</b>\n"
            f"• 10% скидку на первый заказ\n"
            f"• Доступ к бонусной программе\n"
            f"• Лучшие блюда города\n\n"
            f"🎁 <b>Что получаю я:</b>\n"
            f"• 200₽ на счет после твоего заказа\n\n"
            f"📍 Наш ресторан: {settings.RESTAURANT_ADDRESS}"
        )
        
        bot_username = (await callback.bot.get_me()).username
        
        # Создаем клавиатуру для быстрого использования кода
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🛵 Сделать заказ", 
            url=f"https://t.me/{bot_username}?start=ref_{referral_code}"
        )
        
        await callback.message.answer(
            "📤 <b>Сообщение для отправки другу:</b>\n\n"
            "Скопируй или перешли это сообщение 👇",
            parse_mode="HTML"
        )
        
        await callback.message.answer(share_text, parse_mode="HTML", reply_markup=builder.as_markup())
        await callback.answer("✅ Сообщение подготовлено для отправки")
        
    except Exception as e:
        logger.error(f"❌ Error in share_referral_code: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при создании сообщения")

@router.callback_query(F.data == "referral_rules")
async def show_referral_rules(callback: CallbackQuery, l10n: FluentLocalization):
    """Показать правила реферальной программы"""
    try:
        text = (
            "📋 <b>ПРАВИЛА РЕФЕРАЛЬНОЙ ПРОГРАММЫ</b>\n\n"
            
            "💎 <b>Для приглашающего:</b>\n"
            "• Получаешь <b>200₽</b> за каждого друга\n"
            "• Друг должен сделать заказ от <b>500₽</b>\n"
            "• Бонусы начисляются после доставки заказа\n"
            "• Можно использовать для оплаты следующих заказов\n"
            "• Нет ограничений по количеству приглашенных\n\n"
            
            "🎁 <b>Для приглашенного:</b>\n"
            "• Получаешь <b>10% скидку</b> на первый заказ\n"
            "• Скидка действует на заказы от <b>500₽</b>\n"
            "• Можно комбинировать с бонусами\n"
            "• Автоматическая регистрация в бонусной программе\n\n"
            
            "⚡ <b>Как работает:</b>\n"
            "1. Делишься своим реферальным кодом\n"
            "2. Друг вводит код при первом заказе\n"
            "3. Система автоматически начисляет скидку другу\n"
            "4. После доставки заказа ты получаешь 200₽\n\n"
            
            "❓ <b>Частые вопросы:</b>\n"
            "• <i>Можно ли использовать свой код?</i>\n"
            "  Нет, это запрещено правилами\n"
            "• <i>Когда начисляются бонусы?</i>\n"
            "  После успешной доставки первого заказа друга\n"
            "• <i>Сколько друзей можно пригласить?</i>\n"
            "  Неограниченное количество\n"
            "• <i>Куда придут бонусы?</i>\n"
            "  На ваш бонусный счет в карте лояльности\n\n"
            
            "📞 <b>Поддержка:</b>\n"
            "По всем вопросам обращайтесь к администратору"
        )
        
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in show_referral_rules: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при загрузке правил")

@router.callback_query(F.data == "refresh_referral_stats")
async def refresh_referral_stats(callback: CallbackQuery, db_manager: DatabaseManager):
    """Обновление статистики рефералов"""
    try:
        user_id = callback.from_user.id
        
        # Получаем обновленную статистику
        referral_stats = await db_manager.get_referral_stats(user_id)
        referral_code = await db_manager.get_referral_code(user_id)
        
        # Обновляем сообщение
        updated_text = (
            f"👥 <b>ПРИГЛАСИ ДРУГА - ПОЛУЧИ 200₽</b>\n\n"
            
            f"💎 <b>Как это работает:</b>\n"
            f"• Даешь другу свой код\n"
            f"• Друг делает первый заказ от 500₽\n"
            f"• Ты получаешь <b>200₽</b> на счет\n"
            f"• Друг получает <b>10% скидку</b> на первый заказ\n\n"
            
            f"📊 <b>Твоя статистика (обновлено):</b>\n"
            f"• Приглашено друзей: {referral_stats['total_referrals']}\n"
            f"• Успешных приглашений: {referral_stats['completed_referrals']}\n"
            f"• Заработано бонусов: {referral_stats['total_referral_bonus']}₽\n"
            f"• Ожидают заказа: {referral_stats['pending_referrals']}\n\n"
            
            f"🎯 <b>Твой реферальный код:</b>\n"
            f"<code>{referral_code}</code>\n\n"
            
            f"💡 <b>Как делиться кодом:</b>\n"
            f"1. Отправь другу свой код\n"
            f"2. Друг должен ввести его при первом заказе\n"
            f"3. Или перешли готовое сообщение ниже\n"
        )
        
        await callback.message.edit_text(updated_text, parse_mode="HTML")
        await callback.answer("✅ Статистика обновлена")
        
    except Exception as e:
        logger.error(f"❌ Error in refresh_referral_stats: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при обновлении статистики")

@router.message(F.text.regexp(r'^[A-Za-z0-9]{4,20}$'))
async def process_referral_code_input(message: Message, db_manager: DatabaseManager, l10n: FluentLocalization):
    """Обработка ввода реферального кода (формат: ABC123)"""
    try:
        user_id = message.from_user.id
        referral_code = message.text
        
        success = await process_referral_activation(
            user_id=user_id,
            referral_code=referral_code,
            db_manager=db_manager,
            bot=message.bot,
            source="manual_input"
        )
        
        if success:
            success_text = (
                f"✅ <b>Реферальный код активирован!</b>\n\n"
                f"🎁 Теперь вы получите <b>10% скидку</b> на ваш первый заказ!\n\n"
                f"💡 Скидка применится автоматически при оформлении заказа.\n"
                f"💰 Ваш реферер получит 200₽ после вашего первого заказа.\n\n"
                f"🛵 <b>Что дальше?</b>\n"
                f"• Сделайте заказ в разделе '🛵 Доставка'\n"
                f"• Или забронируйте стол в '💺 Бронь стола'\n"
                f"• Скидка применится автоматически!"
            )
            await message.answer(success_text, parse_mode="HTML")
            
            await db_manager.add_user_action(
                user_id=user_id,
                action_type='referral_code_activated',
                action_data={'referral_code': referral_code, 'source': 'manual_input'}
            )
        else:
            await message.answer("❌ Не удалось активировать реферальный код. Возможно:\n• Код неверен\n• У вас уже установлен реферер\n• Вы пытаетесь использовать свой код")
            
    except Exception as e:
        logger.error(f"❌ Error processing referral code: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке реферального кода.")

@router.message(F.text.startswith("ref_"))
async def handle_referral_code_direct(message: Message, db_manager: DatabaseManager, l10n: FluentLocalization):
    """Обработка прямого ввода реферального кода с префиксом ref_"""
    try:
        user_id = message.from_user.id
        referral_code = message.text[4:]  # Убираем "ref_" префикс
        
        if not referral_code:
            await message.answer("❌ Неверный формат реферального кода.")
            return
        
        success = await process_referral_activation(
            user_id=user_id,
            referral_code=referral_code,
            db_manager=db_manager,
            bot=message.bot,
            source="direct_ref"
        )
        
        if success:
            success_text = (
                f"✅ <b>Реферальный код активирован!</b>\n\n"
                f"🎁 Теперь вы получите <b>10% скидку</b> на ваш первый заказ!\n\n"
                f"💡 Скидка применится автоматически при оформлении заказа.\n"
                f"💰 Ваш реферер получит 200₽ после вашего первого заказа.\n\n"
                f"🛵 <b>Что дальше?</b>\n"
                f"• Сделайте заказ в разделе '🛵 Доставка'\n"
                f"• Или забронируйте стол в '💺 Бронь стола'\n"
                f"• Скидка применится автоматически!"
            )
            
            await message.answer(success_text, parse_mode="HTML")
            
            await db_manager.add_user_action(
                user_id=user_id,
                action_type='referral_code_activated_direct',
                action_data={'referral_code': referral_code, 'source': 'direct_ref'}
            )
        else:
            await message.answer("❌ Не удалось активировать реферальный код. Возможно:\n• Код неверен\n• У вас уже установлен реферер\n• Вы пытаетесь использовать свой код")
            
    except Exception as e:
        logger.error(f"❌ Error in handle_referral_code_direct: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке реферального кода.")

async def handle_start_with_referral(user_id: int, referral_code: str, db_manager: DatabaseManager, bot):
    """Обработка реферальной ссылки при команде /start (для использования в main.py)"""
    try:
        success = await process_referral_activation(
            user_id=user_id,
            referral_code=referral_code,
            db_manager=db_manager,
            bot=bot,
            source="start_command"
        )
        
        if success:
            logger.info(f"✅ Referral from start command: user {user_id} -> code {referral_code}")
            return True
        else:
            logger.warning(f"⚠️ Failed to activate referral from start: user {user_id}, code {referral_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error in handle_start_with_referral: {e}", exc_info=True)
        return False