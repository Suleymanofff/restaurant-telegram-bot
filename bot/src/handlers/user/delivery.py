from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Contact, ReplyKeyboardRemove, ContentType, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from fluent.runtime import FluentLocalization
import logging

from src.database.db_manager import DatabaseManager
from src.states.delivery import DeliveryStates
import src.handlers.user.keyboards as kb
from src.utils.rate_limiter import rate_limit
from src.handlers.user.message import show_main_menu
from src.utils.config import settings
from src.states.payment import PaymentStates

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == "🛵 Доставка")
@rate_limit(cooldown=10, action="delivery_start")
async def start_delivery(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager=None):
    """Начало оформления доставки для пользователей"""
        
    try:
        await state.clear()
        await state.update_data(cart=[], delivery_info={})
        
        text = "🍽️ <b>ДОСТАВКА ЕДЫ</b>\n\n"
        text += "🚗 <b>Условия доставки:</b>\n"
        text += "• Минимальный заказ: 500₽\n"
        text += "• Бесплатная доставка от 1500₽\n"
        text += "• Время доставки: 30-45 минут\n"
        text += "• Работаем: 10:00 - 23:00\n\n"
        text += "Выберите категорию:"
        
        await state.set_state(DeliveryStates.choosing_category)
        await message.answer(text, parse_mode="HTML", reply_markup=await kb.get_delivery_categories_kb(l10n))
        
        if db_manager:
            await db_manager.add_user_action(
                user_id=message.from_user.id,
                action_type='delivery_started'
            )
            
    except Exception as e:
        logger.error(f"❌ Error starting delivery: {e}")
        await message.answer("❌ Ошибка при запуске доставки")
        await state.clear()

@router.message(F.text == "🛒 Корзина")
async def view_cart_handler(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Обработчик корзины из любого состояния"""
    await view_cart_from_anywhere(message, state, l10n)

@router.message(DeliveryStates.viewing_menu, F.text == "📋 Категории")
async def back_to_categories_from_menu(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Возврат к категориям из меню"""
    await state.set_state(DeliveryStates.choosing_category)
    await message.answer("Выберите категорию:", reply_markup=await kb.get_delivery_categories_kb(l10n))

@router.message(F.text == "🔙 Назад")
async def back_handler(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager=None):
    """Обработка кнопки Назад"""
    current_state = await state.get_state()
    
    if current_state == DeliveryStates.choosing_category:
        await state.clear()
        await show_main_menu(message, l10n, db_manager)
    elif current_state == DeliveryStates.viewing_menu:
        await state.set_state(DeliveryStates.choosing_category)
        await message.answer("Выберите категорию:", reply_markup=await kb.get_delivery_categories_kb(l10n))
    elif current_state == DeliveryStates.viewing_cart:
        data = await state.get_data()
        current_category_name = data.get('current_category_name', 'меню')
        await state.set_state(DeliveryStates.viewing_menu)
        await message.answer(f"Возвращаемся к {current_category_name}", reply_markup=await kb.get_delivery_menu_kb(l10n))
    else:
        await state.clear()
        await show_main_menu(message, l10n, db_manager)

@router.message(DeliveryStates.choosing_category, F.text.in_(["🍳 ЗАВТРАКИ", "🍲 ГОРЯЧЕЕ", "☕️ ГОРЯЧИЕ НАПИТКИ", "🍸 ХОЛОДНЫЕ НАПИТКИ", "🍰 ДЕСЕРТЫ"]))
async def choose_category(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager=None):
    """Обработка выбора категории"""
    try:
        category_map = {
            '🍳 ЗАВТРАКИ': 'breakfasts',
            '🍲 ГОРЯЧЕЕ': 'hots', 
            '☕️ ГОРЯЧИЕ НАПИТКИ': 'hot_drinks',
            '🍸 ХОЛОДНЫЕ НАПИТКИ': 'cold_drinks',
            '🍰 ДЕСЕРТЫ': 'deserts'
        }
        
        category_key = category_map.get(message.text)
        if not category_key:
            await message.answer("❌ Пожалуйста, выберите категорию из списка")
            return
        
        menu_items = await db_manager.get_delivery_menu(category_key) if db_manager else []
        
        if not menu_items:
            await message.answer("😔 В этой категории пока нет блюд")
            return
        
        await state.update_data(current_category=category_key, current_category_name=message.text)
        
        text = f"<b>{message.text}</b>\n\n"
        
        for item in menu_items:
            text += f"<b>{item['id']}. {item['name']}</b> - {item['price']}₽\n"
            if item.get('description'):
                text += f"<i>{item['description']}</i>\n"
            text += "\n"
        
        text += "💡 <b>Как добавить в корзину:</b>\n"
        text += "• Напишите номер товара (например: <code>1</code>)\n"
        text += "• Или <code>добавить [номер]</code> (например: <code>добавить 1</code>)\n\n"
        text += "🛒 Нажмите 'Корзина' чтобы посмотреть ваш заказ"
        
        await state.set_state(DeliveryStates.viewing_menu)
        await message.answer(text, parse_mode="HTML", reply_markup=await kb.get_delivery_menu_kb(l10n))
        
    except Exception as e:
        logger.error(f"❌ Error choosing category: {e}")
        await message.answer("❌ Ошибка при загрузке меню")

@router.message(DeliveryStates.viewing_menu, F.text)
async def add_to_cart_flexible(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager=None):
    """Гибкое добавление товара в корзину"""
    try:
        text = message.text.lower().strip()
        
        if text == "🔙 назад":
            await state.set_state(DeliveryStates.choosing_category)
            await message.answer("Выберите категорию:", reply_markup=await kb.get_delivery_categories_kb(l10n))
            return
            
        if text == "📋 категории":
            await state.set_state(DeliveryStates.choosing_category)
            await message.answer("Выберите категорию:", reply_markup=await kb.get_delivery_categories_kb(l10n))
            return
        
        item_id = None
        if text.isdigit():
            item_id = int(text)
        elif text.startswith('добавить') and len(text.split()) > 1:
            try:
                item_id = int(text.split()[1])
            except ValueError:
                pass
        
        if not item_id:
            await message.answer("❌ Укажите номер товара. Например: '1' или 'добавить 1'")
            return
        
        data = await state.get_data()
        current_category = data.get('current_category', 'pizza')
        menu_items = await db_manager.get_delivery_menu(current_category) if db_manager else []
        
        item = next((item for item in menu_items if item['id'] == item_id), None)
        
        if not item:
            await message.answer("❌ Товар с таким номером не найден. Используйте номер из списка.")
            return
        
        cart = data.get('cart', [])
        existing_item = next((cart_item for cart_item in cart if cart_item['id'] == item['id']), None)
        
        if existing_item:
            existing_item['quantity'] += 1
        else:
            cart.append({
                'id': item['id'],
                'name': item['name'],
                'price': float(item['price']),
                'quantity': 1
            })
        
        await state.update_data(cart=cart)
        total = sum(item['price'] * item['quantity'] for item in cart)
        
        await message.answer(
            f"✅ <b>{item['name']}</b> добавлен в корзину\n\n"
            f"🛒 В корзине: {len(cart)} позиций\n"
            f"💰 Общая сумма: {total}₽",
            parse_mode="HTML"
        )
        
        if db_manager:
            await db_manager.add_user_action(
                user_id=message.from_user.id,
                action_type='delivery_item_added',
                action_data={'item_id': item['id'], 'item_name': item['name']}
            )
            
    except Exception as e:
        logger.error(f"❌ Error adding to cart: {e}")
        await message.answer("❌ Ошибка при добавлении в корзину")

@router.message(DeliveryStates.viewing_cart, F.text == "✅ Оформить заказ")
async def start_checkout(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager = None):
    """Начало оформления заказа с расчетом скидок и бонусов"""
    try:
        data = await state.get_data()
        cart = data.get('cart', [])
        
        if not cart:
            await message.answer("🛒 Корзина пуста! Добавьте товары перед оформлением.")
            return
        
        # Базовая сумма товаров
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        
        # Проверяем минимальный заказ
        if subtotal < 500:
            await message.answer(
                f"❌ Минимальная сумма заказа 500₽\n"
                f"💰 Ваша сумма: {subtotal}₽\n"
                f"📦 Добавьте товаров еще на {500 - subtotal}₽"
            )
            return
        
        # Расчет доставки
        delivery_cost = 0 if subtotal >= 1500 else 200
        total_before_discount = subtotal + delivery_cost
        
        # Проверяем, есть ли у пользователя реферер и применяем скидку
        user = await db_manager.get_user(message.from_user.id)
        discount = 0
        
        logger.info(f"🔍 Start checkout: user_id={message.from_user.id}, has_referrer={user and user.get('referrer_id')}")
        
        if user and user.get('referrer_id'):
            is_first = await is_first_order(message.from_user.id, db_manager)
            logger.info(f"🔍 First order check in checkout: {is_first}")
            if is_first:
                discount = total_before_discount * 0.10
                logger.info(f"🔍 Applying 10% discount in checkout: {discount}₽")
        
        total_after_discount = total_before_discount - discount
        
        # Получаем бонусный баланс
        bonus_balance = await db_manager.get_user_bonus_balance(message.from_user.id)
        max_bonus_usage = total_after_discount * 0.6  # Можно использовать до 60% от суммы
        
        # Сохраняем расчеты для использования на следующих шагах
        await state.update_data(
            subtotal=subtotal,
            delivery_cost=delivery_cost,
            total_before_discount=total_before_discount,
            discount=discount,
            total_after_discount=total_after_discount,
            bonus_balance=bonus_balance,
            max_bonus_usage=max_bonus_usage
        )
        
        logger.info(f"🔢 Checkout totals: subtotal={subtotal}, delivery={delivery_cost}, discount={discount}, total_after_discount={total_after_discount}")
        
        text = "📝 <b>ОФОРМЛЕНИЕ ЗАКАЗА</b>\n\n"
        text += f"🛒 <b>Ваш заказ:</b>\n"
        
        for item in cart:
            text += f"• {item['name']} x{item['quantity']} - {item['price'] * item['quantity']}₽\n"
        
        text += f"\n💰 <b>Сумма товаров:</b> {subtotal}₽\n"
        
        if delivery_cost > 0:
            text += f"🚗 <b>Доставка:</b> {delivery_cost}₽\n"
        else:
            text += f"🎉 <b>Доставка:</b> бесплатно!\n"
        
        # Показываем скидку, если она уже есть
        if discount > 0:
            text += f"🎁 <b>Реферальная скидка 10%:</b> -{discount:.0f}₽\n"
        
        text += f"💰 <b>Итого к оплате:</b> {total_after_discount}₽\n\n"
        
        if bonus_balance > 0:
            text += f"💳 <b>Ваш бонусный баланс:</b> {bonus_balance}₽\n"
            text += f"💎 <b>Можно использовать:</b> до {max_bonus_usage:.0f}₽\n\n"
        
        text += "Пожалуйста, введите ваше <b>имя</b>:"
        
        await state.set_state(DeliveryStates.entering_name)
        await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        
    except Exception as e:
        logger.error(f"❌ Error starting checkout: {e}")
        await message.answer("❌ Ошибка при оформлении заказа")

@router.message(DeliveryStates.entering_name, F.text)
async def enter_customer_name(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Ввод имени клиента"""
    name = message.text.strip()
    
    if len(name) < 2:
        await message.answer("❌ Имя должно содержать минимум 2 символа. Введите еще раз:")
        return
    
    await state.update_data(customer_name=name)
    await state.set_state(DeliveryStates.entering_phone)
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Отправить телефон", request_contact=True)
    builder.button(text="🔙 Назад")
    builder.adjust(1)
    
    await message.answer(
        f"👤 Имя: <b>{name}</b>\n\n"
        "Теперь введите ваш <b>номер телефона</b> или нажмите 'Отправить телефон':",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.message(DeliveryStates.entering_phone, F.contact)
async def enter_phone_from_contact(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Обработка телефона из контакта"""
    phone = message.contact.phone_number
    await process_phone_number(message, state, phone)

@router.message(DeliveryStates.entering_phone, F.text)
async def enter_phone_manual(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Обработка ручного ввода телефона"""
    if message.text == "🔙 Назад":
        await state.set_state(DeliveryStates.viewing_cart)
        await view_cart_from_anywhere(message, state, l10n)
        return
    
    phone = message.text.strip()
    await process_phone_number(message, state, phone)

async def process_phone_number(message: Message, state: FSMContext, phone: str):
    """Общая обработка номера телефона"""
    clean_phone = ''.join(filter(str.isdigit, phone))
    
    if len(clean_phone) < 10:
        await message.answer("❌ Неверный формат телефона. Введите еще раз:")
        return
    
    await state.update_data(customer_phone=clean_phone)
    await state.set_state(DeliveryStates.entering_address)
    
    await message.answer(
        f"📞 Телефон: <b>{clean_phone}</b>\n\n"
        "Теперь введите <b>адрес доставки</b> (улица, дом, квартира):",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(DeliveryStates.entering_address, F.text)
async def enter_delivery_address_with_referral(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager = None):
    """Ввод адреса доставки с последующим предложением ввести реферальный код"""
    address = message.text.strip()
    
    if len(address) < 10:
        await message.answer("❌ Адрес должен содержать минимум 10 символов. Введите еще раз:")
        return
    
    await state.update_data(delivery_address=address)
    
    # Проверяем, есть ли у пользователя уже реферер
    user = await db_manager.get_user(message.from_user.id)
    has_referrer = user and user.get('referrer_id')
    
    if has_referrer:
        # Если реферер уже есть, переходим к использованию бонусов
        await state.set_state(DeliveryStates.using_bonus)
        await process_bonus_step(message, state, db_manager)
    else:
        # Предлагаем ввести реферальный код
        await state.set_state(DeliveryStates.entering_referral)
        
        text = (
            f"🏠 <b>Адрес доставки сохранен:</b> {address}\n\n"
            f"🎁 <b>Есть реферальный код?</b>\n\n"
            f"Если друг дал вам реферальный код, введите его сейчас и получите <b>10% скидку</b> на первый заказ!\n\n"
            f"💡 <b>Что дает реферальный код:</b>\n"
            f"• <b>10% скидка</b> на ваш первый заказ\n"
            f"• Ваш друг получит <b>200₽</b> на счет\n"
            f"• Вы оба становитесь участниками бонусной программы\n\n"
            f"📝 <b>Введите реферальный код:</b>\n"
            f"(или отправьте <code>0</code> чтобы пропустить)"
        )
        
        builder = ReplyKeyboardBuilder()
        builder.button(text="🚫 Пропустить")
        builder.adjust(1)
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())



@router.message(DeliveryStates.entering_referral, F.text)
async def enter_referral_code_during_checkout(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager = None):
    """Обработка ввода реферального кода во время оформления заказа"""
    try:
        user_input = message.text.strip()
        
        # Если пользователь хочет пропустить
        if user_input in ["0", "🚫 Пропустить", "пропустить", "skip"]:
            await state.set_state(DeliveryStates.using_bonus)
            await process_bonus_step(message, state, db_manager)
            return
        
        # Обрабатываем реферальный код
        referral_code = user_input.upper()
        
        logger.info(f"🔍 Processing referral code: {referral_code} for user {message.from_user.id}")
        
        # Проверяем, не пытается ли пользователь использовать свой код
        user_referral_code = await db_manager.get_referral_code(message.from_user.id)
        if referral_code == user_referral_code:
            await message.answer("❌ Нельзя использовать свой собственный реферальный код! Введите другой код или отправьте '0' чтобы пропустить:")
            return
        
        # Ищем пользователя по реферальному коду
        referrer = await db_manager.get_user_by_referral_code(referral_code)
        if not referrer:
            await message.answer("❌ Реферальный код не найден. Проверьте правильность кода или отправьте '0' чтобы пропустить:")
            return
        
        # Проверяем, что реферер не является самим пользователем
        if referrer['user_id'] == message.from_user.id:
            await message.answer("❌ Нельзя использовать свой собственный код! Введите другой код или отправьте '0' чтобы пропустить:")
            return
        
        # Устанавливаем реферера
        success = await db_manager.set_user_referrer(message.from_user.id, referrer['user_id'])
        if success:
            # Создаем запись о реферальном бонусе
            await db_manager.add_referral_bonus(
                referrer_id=referrer['user_id'],
                referred_id=message.from_user.id,
                bonus_amount=200.00
            )
            
            # ПЕРЕСЧИТЫВАЕМ ЗАКАЗ С УЧЕТОМ СКИДКИ
            logger.info(f"🔍 Before recalculation for user {message.from_user.id}")
            new_totals = await recalculate_order_after_referral(state, db_manager, message.from_user.id)
            logger.info(f"🔍 After recalculation: discount={new_totals['discount']}, total_after_discount={new_totals['total_after_discount']}")
            
            # Уведомляем реферера
            try:
                referrer_notification = (
                    f"🎉 <b>У вас новый реферал!</b>\n\n"
                    f"👤 Пользователь: {message.from_user.full_name}\n"
                    f"💎 Использовал ваш код: {referral_code}\n\n"
                    f"💰 Вы получите <b>200₽</b> после его первого заказа!\n"
                    f"💳 Следите за статусом в разделе '💳 Карта лояльности'"
                )
                await message.bot.send_message(
                    chat_id=referrer['user_id'],
                    text=referrer_notification,
                    parse_mode="HTML"
                )
            except Exception as notify_error:
                logger.error(f"❌ Failed to notify referrer: {notify_error}")
            
            # Сообщение пользователю с НОВОЙ СУММОЙ
            success_text = (
                f"✅ <b>Реферальный код активирован!</b>\n\n"
                f"🎁 Вы получили <b>10% скидку</b> на этот заказ!\n"
            )
            
            if new_totals['discount'] > 0:
                success_text += f"💰 Скидка составила: <b>-{new_totals['discount']:.0f}₽</b>\n\n"
                success_text += f"💡 Скидка применена к вашему заказу.\n"
                success_text += f"💰 <b>Новая сумма к оплате:</b> {new_totals['total_after_discount']}₽\n\n"
            else:
                success_text += f"⚠️ <b>Но скидка не была применена!</b>\n"
                success_text += f"💰 Сумма к оплате: {new_totals['total_after_discount']}₽\n\n"
                success_text += f"ℹ️ Скидка применяется только к первому заказу.\n\n"
            
            success_text += f"🎉 Ваш реферер получит 200₽ после завершения заказа."
            
            await message.answer(success_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
            
            # Логируем действие
            await db_manager.add_user_action(
                user_id=message.from_user.id,
                action_type='referral_code_activated_during_checkout',
                action_data={'referrer_id': referrer['user_id'], 'referral_code': referral_code, 'discount': new_totals['discount']}
            )
            
            logger.info(f"✅ Referral code activated during checkout: user {message.from_user.id} -> referrer {referrer['user_id']}, discount: {new_totals['discount']}₽")
            
        else:
            await message.answer("❌ Ошибка при активации реферального кода. Введите код еще раз или отправьте '0' чтобы пропустить:")
            return
        
        # Переходим к использованию бонусов
        await state.set_state(DeliveryStates.using_bonus)
        await process_bonus_step(message, state, db_manager)
            
    except Exception as e:
        logger.error(f"❌ Error processing referral code during checkout: {e}")
        await message.answer("❌ Произошла ошибка при обработке реферального кода. Введите код еще раз или отправьте '0' чтобы пропустить:")



async def process_bonus_step(message: Message, state: FSMContext, db_manager: DatabaseManager):
    """Обработка шага использования бонусов после ввода реферального кода"""
    try:
        # Получаем данные для бонусов
        data = await state.get_data()
        total_after_discount = data.get('total_after_discount', 0)
        bonus_balance = await db_manager.get_user_bonus_balance(message.from_user.id)
        max_bonus_usage = total_after_discount * 0.6  # Можно использовать до 60% от суммы
        
        text = f"💰 <b>Сумма к оплате:</b> {total_after_discount}₽\n"
        
        if bonus_balance > 0:
            text += (
                f"\n💳 <b>Ваш бонусный баланс:</b> {bonus_balance}₽\n"
                f"💎 <b>Можно использовать:</b> до {max_bonus_usage:.0f}₽\n\n"
                f"💡 <b>Как использовать бонусы?</b>\n"
                f"• Введите сумму бонусов для списания\n"
                f"• Можно использовать до 60% от суммы заказа\n"
                f"• Или введите 0, если не хотите использовать бонусы\n\n"
                f"<b>Сколько бонусов использовать?</b>"
            )
        else:
            text += "\n💡 У вас пока нет бонусов для использования.\nВведите 0 чтобы продолжить:"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Error in process_bonus_step: {e}")
        await message.answer("❌ Ошибка при переходе к использованию бонусов.")


@router.message(DeliveryStates.using_bonus, F.text)
async def enter_bonus_amount(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager = None):
    """Обработка ввода суммы бонусов для списания"""
    try:
        bonus_used = float(message.text.strip())
        
        if bonus_used < 0:
            await message.answer("❌ Сумма бонусов не может быть отрицательной. Введите еще раз:")
            return
        
        data = await state.get_data()
        total_after_discount = data.get('total_after_discount', 0)
        bonus_balance = data.get('bonus_balance', 0)
        max_bonus_usage = data.get('max_bonus_usage', 0)
        discount = data.get('discount', 0)
        
        available_bonus = min(bonus_balance, max_bonus_usage)
        
        if bonus_used > available_bonus:
            await message.answer(
                f"❌ Недостаточно бонусов. Доступно: {available_bonus:.0f}₽\n"
                f"Введите сумму еще раз:"
            )
            return
        
        if bonus_used > max_bonus_usage:
            await message.answer(
                f"❌ Можно использовать не более {max_bonus_usage:.0f}₽ (60% от суммы заказа)\n"
                f"Введите сумму еще раз:"
            )
            return
        
        # Сохраняем сумму использованных бонусов
        await state.update_data(bonus_used=bonus_used)
        await state.set_state(DeliveryStates.confirming_order)
        
        # Считаем итоговую сумму
        final_amount = total_after_discount - bonus_used
        
        # Формируем текст подтверждения
        text = "✅ <b>ПОДТВЕРЖДЕНИЕ ЗАКАЗА</b>\n\n"
        text += f"👤 <b>Имя:</b> {data['customer_name']}\n"
        text += f"📞 <b>Телефон:</b> {data['customer_phone']}\n"
        text += f"🏠 <b>Адрес:</b> {data['delivery_address']}\n\n"
        
        text += "<b>Состав заказа:</b>\n"
        cart = data.get('cart', [])
        for item in cart:
            text += f"• {item['name']} x{item['quantity']} - {item['price'] * item['quantity']}₽\n"
        
        text += f"\n💰 <b>Сумма товаров:</b> {data.get('subtotal', 0)}₽\n"
        
        delivery_cost = data.get('delivery_cost', 0)
        if delivery_cost > 0:
            text += f"🚗 <b>Доставка:</b> {delivery_cost}₽\n"
        else:
            text += f"🎉 <b>Доставка:</b> бесплатно!\n"
        
        # Показываем скидку, если она была применена
        if discount > 0:
            text += f"🎁 <b>Реферальная скидка 10%:</b> -{discount:.0f}₽\n"
        
        if bonus_used > 0:
            text += f"💎 <b>Использовано бонусов:</b> -{bonus_used:.0f}₽\n"
        
        text += f"\n💵 <b>Итого к оплате:</b> {final_amount}₽\n\n"

        text += "Подтвердить заказ?"
        
        builder = ReplyKeyboardBuilder()
        builder.button(text="✅ Подтвердить заказ")
        builder.button(text="❌ Отменить")
        builder.adjust(1)
        
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму:")

# @router.message(DeliveryStates.confirming_order, F.text == "✅ Подтвердить заказ")
# async def confirm_delivery_order(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager = None):
#     """Финальное подтверждение и создание заказа с бонусной системой"""
#     try:
#         data = await state.get_data()
#         cart = data.get('cart', [])
#         customer_name = data.get('customer_name')
#         customer_phone = data.get('customer_phone')
#         delivery_address = data.get('delivery_address')
#         bonus_used = data.get('bonus_used', 0)
#         discount = data.get('discount', 0)
#         subtotal = data.get('subtotal', 0)
#         delivery_cost = data.get('delivery_cost', 0)
#         total_before_discount = data.get('total_before_discount', 0)
        
#         if not cart:
#             await message.answer("❌ Ошибка: корзина пуста")
#             await state.clear()
#             return
        
#         # Финальный расчет
#         total_after_discount = total_before_discount - discount
#         final_amount = total_after_discount - bonus_used
        
#         # Формируем данные заказа
#         order_data = {
#             'items': cart,
#             'subtotal': subtotal,
#             'delivery_cost': delivery_cost,
#             'total': total_before_discount,  # Сумма до применения скидок и бонусов
#             'discount': discount,
#             'bonus_used': bonus_used,
#             'final_amount': final_amount,
#             'delivery_address': delivery_address,
#             'customer_name': customer_name,
#             'customer_phone': customer_phone,
#             'delivery_time': 'Как можно скорее'
#         }
        
#         # Создаем заказ в БД
#         order_id = await db_manager.create_delivery_order(
#             user_id=message.from_user.id,
#             order_data=order_data,
#             discount_amount=discount,
#             bonus_used=bonus_used,
#             final_amount=final_amount
#         )
        
#         if order_id:
#             # 🔥 НАЧИСЛЯЕМ КЕШБЭК 5% ОТ ЗАКАЗА
#             cashback_amount = await db_manager.calculate_order_cashback(final_amount)
#             if cashback_amount > 0:
#                 await db_manager.add_bonus_transaction(
#                     user_id=message.from_user.id,
#                     amount=cashback_amount,
#                     transaction_type='cashback',
#                     description=f'Кешбэк 5% от заказа #{order_id}',
#                     order_id=order_id
#                 )
#                 logger.info(f"💎 Начислен кешбэк {cashback_amount}₽ пользователю {message.from_user.id} за заказ #{order_id}")
            
#             # 🔥 ЗАПИСЫВАЕМ СПИСАНИЕ БОНУСОВ (если использовались)
#             if bonus_used > 0:
#                 await db_manager.add_bonus_transaction(
#                     user_id=message.from_user.id,
#                     amount=-bonus_used,
#                     transaction_type='purchase',
#                     description=f'Оплата заказа #{order_id} бонусами',
#                     order_id=order_id
#                 )
#                 logger.info(f"💳 Списано бонусов {bonus_used}₽ с пользователя {message.from_user.id} за заказ #{order_id}")
            
#             # 🔥 ОБРАБАТЫВАЕМ РЕФЕРАЛЬНЫЕ БОНУСЫ
#             user = await db_manager.get_user(message.from_user.id)
#             if user and user.get('referrer_id') and discount > 0:
#                 success = await db_manager.complete_referral_bonus(message.from_user.id, order_id)
#                 if success:
#                     try:
#                         # Получаем актуальный баланс реферера после начисления
#                         referrer = await db_manager.get_user(user['referrer_id'])
#                         bonus_notification = (
#                             f"💰 <b>Вам начислен реферальный бонус!</b>\n\n"
#                             f"👤 {customer_name} сделал(а) первый заказ.\n"
#                             f"🎁 Вам начислено: <b>200₽</b> на счет\n"
#                             f"💳 Теперь ваш баланс: {referrer.get('bonus_balance', 0)}₽"
#                         )
#                         await message.bot.send_message(
#                             chat_id=user['referrer_id'],
#                             text=bonus_notification,
#                             parse_mode="HTML"
#                         )
#                         logger.info(f"👥 Начислен реферальный бонус 200₽ пользователю {user['referrer_id']}")
#                     except Exception as notify_error:
#                         logger.error(f"❌ Failed to notify referrer about bonus: {notify_error}")
            
#             # 🔥 ФОРМИРУЕМ СООБЩЕНИЕ ОБ УСПЕХЕ
#             success_text = (
#                 f"🎉 <b>ЗАКАЗ ПРИНЯТ!</b>\n\n"
#                 f"🛵 <b>Номер заказа:</b> #{order_id}\n"
#             )
            
#             # Показываем скидку, если она была применена
#             if discount > 0:
#                 success_text += f"🎁 <b>Реферальная скидка 10%:</b> -{discount:.0f}₽\n"
            
#             # Показываем использованные бонусы
#             if bonus_used > 0:
#                 success_text += f"💎 <b>Использовано бонусов:</b> -{bonus_used:.0f}₽\n"
            
#             # 🔥 ПОКАЗЫВАЕМ НАЧИСЛЕННЫЙ КЕШБЭК
#             if cashback_amount > 0:
#                 success_text += f"💳 <b>Начислено кешбэка:</b> +{cashback_amount:.0f}₽\n"
            
#             success_text += (
#                 f"💰 <b>Итоговая сумма:</b> {final_amount}₽\n"
#                 f"⏰ <b>Время доставки:</b> 30-45 минут\n"
#                 f"🏠 <b>Адрес:</b> {delivery_address}\n\n"
#                 f"📞 Мы свяжемся с вами для подтверждения: {customer_phone}\n\n"
#                 f"<i>Спасибо за заказ! Приятного аппетита! 🍕</i>"
#             )
            
#             await message.answer(success_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
            
#             # 🔥 УВЕДОМЛЕНИЕ АДМИНИСТРАТОРОВ
#             await notify_admins_about_delivery_order(
#                 bot=message.bot,
#                 order_id=order_id,
#                 order_data=order_data,
#                 customer_name=customer_name,
#                 customer_phone=customer_phone,
#                 total=final_amount,
#                 delivery_address=delivery_address,
#                 db_manager=db_manager
#             )
            
#             # 🔥 ЛОГИРУЕМ ДЕЙСТВИЕ
#             await db_manager.add_user_action(
#                 user_id=message.from_user.id,
#                 action_type='delivery_order_created',
#                 action_data={
#                     'order_id': order_id, 
#                     'total': final_amount, 
#                     'discount': discount, 
#                     'bonus_used': bonus_used,
#                     'cashback_earned': cashback_amount
#                 }
#             )
            
#             logger.info(f"✅ Delivery order #{order_id} created by user {message.from_user.id}, cashback: {cashback_amount}₽")
            
#             # 🔥 ОЧИЩАЕМ СОСТОЯНИЕ И ПОКАЗЫВАЕМ ГЛАВНОЕ МЕНЮ
#             await state.clear()
#             await show_main_menu(message, l10n, db_manager)
            
#         else:
#             await message.answer("❌ Ошибка при создании заказа. Попробуйте позже.")
#             await state.clear()
            
#     except Exception as e:
#         logger.error(f"❌ Error confirming delivery order: {e}", exc_info=True)
#         await message.answer("❌ Произошла ошибка при оформлении заказа")
#         await state.clear()


@router.message(DeliveryStates.confirming_order, F.text == "✅ Подтвердить заказ")
async def confirm_delivery_ask_payment(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Перед созданием заказа спрашиваем способ оплаты"""
    try:
        data = await state.get_data()
        # если вдруг корзина пуста — стандартная защита
        if not data.get('cart'):
            await message.answer("❌ Корзина пуста. Вернитесь в меню и добавьте блюда.")
            await state.clear()
            return

        text = "Выберите способ оплаты:\n\n"
        text += "💵 — Оплата курьеру при получении\n"
        text += "💳 — Оплата по реквизитам (перевод / карта). После перевода отправьте скрин.\n\n"
        text += "Выберите вариант:"

        builder = ReplyKeyboardBuilder()
        builder.button(text="💵 Курьеру наличными")
        builder.button(text="💳 По реквизитам (отправить скрин)")
        builder.button(text="❌ Отменить")
        builder.adjust(1)

        await state.set_state(PaymentStates.choosing_payment_method)
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

    except Exception as e:
        logger.error(f"❌ Error asking payment method: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте ещё раз.")
        await state.clear()


@router.message(PaymentStates.choosing_payment_method, F.text == "💵 Курьеру наличными")
async def payment_cash_on_delivery(
    message: Message,
    state: FSMContext,
    l10n: FluentLocalization,
    db_manager: DatabaseManager = None
):
    """Пользователь выбрал оплату курьеру — создаём заказ, фиксируем способ оплаты и уведомляем админов."""
    try:
        data = await state.get_data()
        # Защита: если корзина вдруг пустая
        if not data.get('cart'):
            await message.answer("❌ Корзина пуста. Пожалуйста, добавьте блюда в корзину.")
            await state.clear()
            return

        # --- Формируем order_data и явно указываем способ оплаты ---
        order_data = {
            'items': data.get('cart', []),
            'subtotal': data.get('subtotal', 0),
            'delivery_cost': data.get('delivery_cost', 0),
            'total': data.get('total_before_discount', 0),
            'discount': data.get('discount', 0),
            'bonus_used': data.get('bonus_used', 0),
            'final_amount': (data.get('total_after_discount', 0) - data.get('bonus_used', 0)),
            'delivery_address': data.get('delivery_address'),
            'customer_name': data.get('customer_name'),
            'customer_phone': data.get('customer_phone'),
            'delivery_time': data.get('delivery_time', 'Как можно скорее'),
            # ВАЖНО: сохраняем способ оплаты прямо в order_data
            'payment_method': 'cash'
        }

        # Создаём заказ в БД
        order_id = await db_manager.create_delivery_order(
            user_id=message.from_user.id,
            order_data=order_data,
            discount_amount=data.get('discount', 0),
            bonus_used=data.get('bonus_used', 0),
            final_amount=order_data['final_amount']
        )

        if not order_id:
            await message.answer("❌ Ошибка при создании заказа. Попробуйте позже.", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return

        # Явно задать способ оплаты в отдельном поле таблицы (на случай, если create_delivery_order не делает этого)
        await db_manager.update_order_payment_method(order_id, 'cash')

        # (Опционально) сразу перевести в preparing — оставляю логику как ранее
        await db_manager.update_delivery_order_status(order_id, 'preparing')

        # --- Ответ пользователю: указываем способ оплаты ---
        success_text = (
            f"✅ <b>Заказ оформлен #{order_id}</b>\n\n"
            f"💰 Итоговая сумма: {order_data['final_amount']}₽\n"
            f"⏰ Время доставки: 30-45 минут\n"
            f"🏠 Адрес: {order_data['delivery_address']}\n\n"
            f"📞 Мы свяжемся с вами: {order_data['customer_phone']}\n\n"
            f"<i>Оплата: наличными курьеру при получении</i>"
        )
        await message.answer(success_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())

        # --- Оповещение админам: передаём полный order_data с payment_method и формируем понятный текст ---
        admin_text = (
            f"🆕 <b>Новый заказ #{order_id}</b>\n\n"
            f"Клиент: {order_data['customer_name']} (ID {message.from_user.id})\n"
            f"Телефон: {order_data['customer_phone']}\n"
            f"Адрес: {order_data['delivery_address']}\n\n"
            f"Сумма: {order_data['final_amount']}₽\n"
            f"Оплата: <b>Наличными курьеру</b>\n\n"
            f"Нажмите кнопку, чтобы принять заказ в работу."
        )

        # Используем функцию уведомления админов — передаём order_id и order_data
        # Если notify_admins_about_delivery_order умеет принимать текст — можно подставить admin_text.
        await notify_admins_about_delivery_order(
            bot=message.bot,
            order_id=order_id,
            order_data=order_data,
            customer_name=order_data['customer_name'],
            customer_phone=order_data['customer_phone'],
            total=order_data['final_amount'],
            delivery_address=order_data['delivery_address'],
            db_manager=db_manager,
            custom_admin_message=admin_text  # <-- если функция поддерживает кастомный текст
        )

        # Лог действия и очистка состояния
        await db_manager.add_user_action(
            user_id=message.from_user.id,
            action_type='delivery_order_created',
            action_data={'order_id': order_id, 'payment_method': 'cash'}
        )

        await state.clear()
        await show_main_menu(message, l10n, db_manager)

    except Exception as e:
        logger.error(f"❌ Error creating cash-on-delivery order: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при оформлении заказа.")
        await state.clear()


@router.message(PaymentStates.choosing_payment_method, F.text == "💳 По реквизитам (отправить скрин)")
async def payment_by_requisites(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager: DatabaseManager = None):
    """Пользователь выбрал оплату по реквизитам — создаём заказ и просим прислать скрин"""
    try:
        data = await state.get_data()

        order_data = {
            'items': data.get('cart', []),
            'subtotal': data.get('subtotal', 0),
            'delivery_cost': data.get('delivery_cost', 0),
            'total': data.get('total_before_discount', 0),
            'discount': data.get('discount', 0),
            'bonus_used': data.get('bonus_used', 0),
            'final_amount': data.get('total_after_discount', 0) - data.get('bonus_used', 0),
            'delivery_address': data.get('delivery_address'),
            'customer_name': data.get('customer_name'),
            'customer_phone': data.get('customer_phone'),
            'delivery_time': data.get('delivery_time', 'Как можно скорее')
        }

        order_id = await db_manager.create_delivery_order(
            user_id=message.from_user.id,
            order_data=order_data,
            discount_amount=data.get('discount', 0),
            bonus_used=data.get('bonus_used', 0),
            final_amount=order_data['final_amount']
        )

        if not order_id:
            await message.answer("❌ Ошибка при создании заказа. Попробуйте позже.", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return

        # Сохраняем способ оплаты 'card' (или 'bank_transfer')
        await db_manager.update_order_payment_method(order_id, 'card')
        # Оставляем payment_status = 'pending' (админ подтвердит после проверки скрина)

        # Сохраняем order_id в состоянии, чтобы потом принять скрин
        await state.update_data(pending_payment_order_id=order_id)

        # Отправляем инструкцию пользователю (вставьте свои реквизиты вручную или подставьте из settings)
        payment_info = (
            "Пожалуйста, оплатите переводом на следующие реквизиты и пришлите скрин оплаты:\n\n"
            "• Номер карты: <b>0000 0000 0000 0000</b>\n"
            "• Получатель: ООО «Ресторан»\n"
            "• Назначение: оплата заказа #{order_id}\n\n"
            "После перевода отправьте сюда скрин (фото) или нажмите «Я оплатил» и прикрепите скрин."
        ).format(order_id=order_id)

        await message.answer(payment_info, parse_mode="HTML")
        await message.answer("📎 Отправьте скрин оплаты (фото) прямо в чат.", reply_markup=ReplyKeyboardBuilder().button(text="❌ Отменить").adjust(1).as_markup())

        await state.set_state(PaymentStates.waiting_payment_confirmation)

    except Exception as e:
        logger.error(f"❌ Error creating card-transfer order: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при оформлении заказа.")
        await state.clear()

@router.message(PaymentStates.waiting_payment_confirmation, F.content_type.in_({ContentType.PHOTO, ContentType.TEXT}))
async def handle_payment_proof(message: Message, state: FSMContext, db_manager: DatabaseManager = None):
    """Приём скрина оплаты (фото) или текстового уведомления"""
    try:
        data = await state.get_data()
        order_id = data.get('pending_payment_order_id')
        if not order_id:
            await message.answer("❌ Не найден связанный заказ. Пожалуйста, начните оформление заново.")
            await state.clear()
            return

        # Если пользователь прислал фото
        if message.photo:
            # Берём самый большой вариант
            file_id = message.photo[-1].file_id
            note = "screenshot"

            # Сохраняем receipt в БД (нужно реализовать save_payment_receipt в db_manager)
            await db_manager.save_payment_receipt(order_id=order_id, user_id=message.from_user.id, file_id=file_id, note=note)

            # Пересылаем скрин админам с кнопками подтверждения
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Подтвердить оплату", callback_data=f"payment_confirm_{order_id}")
            builder.button(text="❌ Отклонить оплату", callback_data=f"payment_reject_{order_id}")
            builder.adjust(1)

            # Попробуем получить заказ и собрать детальную карточку
            try:
                order = await db_manager.get_delivery_order_by_id(order_id)
            except Exception as e:
                logger.debug(f"Failed to fetch order #{order_id}: {e}")
                order = None

            # helpers (локальные, чтобы не требовать внешних импортов)
            import json
            import html
            import re

            def _strip_html_tags(text: str) -> str:
                return re.sub(r'<[^>]+>', '', text) if text else ""

            def _make_short(text: str, plain_limit: int = 1000, cut_chars: int = 900) -> str:
                """Если plain-текст длинный — обрезаем безопасно по символам (до cut_chars)."""
                if len(_strip_html_tags(text)) <= plain_limit:
                    return text
                # обрежем по видимым символам (без HTML-тегов) — простая обрезка
                plain = _strip_html_tags(text)
                cut = plain[:cut_chars].rstrip()
                return html.escape(cut) + "..."

            # Стартуем с базового блока (в любом случае)
            basic_info = (
                f"💳 <b>ПРИНЯТ СКРИН ОПЛАТЫ</b>\n\n"
                f"Номер заказа: #{order_id}\n"
                f"Клиент: {html.escape(message.from_user.full_name or '')} (ID {message.from_user.id})\n"
            )

            # Если есть заказ — дополняем деталями
            if order:
                # Разбираем order_data (поддержка JSON-строки или dict)
                order_data = order.get('order_data') or {}
                if isinstance(order_data, str):
                    try:
                        order_data = json.loads(order_data)
                    except Exception:
                        order_data = {}

                items = []
                if isinstance(order_data, dict):
                    items = order_data.get('items', []) or []

                # Формируем строки по позициям: "Пицца x2 — 500₽"
                item_lines = []
                for it in items:
                    try:
                        name = html.escape(str(it.get('name', '—')))
                        qty = int(it.get('quantity', 1)) if it.get('quantity') is not None else 1
                        price = float(it.get('price', 0) or 0)
                        line_total = int(price * qty)
                        item_lines.append(f"• {name} x{qty} — {line_total}₽")
                    except Exception:
                        # при проблемах с конкретной позицией просто пропускаем
                        continue

                items_text = "\n".join(item_lines) if item_lines else "• (состав не указан)"

                # Суммы и скидки
                total_amount = int(order.get('total_amount') or 0)
                final_amount = int(order.get('final_amount') or total_amount)
                discount_amount = int(order.get('discount_amount') or 0)
                bonus_used = int(order.get('bonus_used') or 0)

                # Оплата
                payment_method = order.get('payment_method') or (order_data.get('payment_method') if isinstance(order_data, dict) else None) or "—"
                payment_status = order.get('payment_status') or "—"

                # Контакт / адрес
                customer_phone = html.escape(str(order.get('customer_phone') or "—"))
                delivery_addr = html.escape(str(order.get('delivery_address') or "—"))

                details = (
                    f"Телефон: {customer_phone}\n"
                    f"Адрес: {delivery_addr}\n\n"
                    f"<b>Состав заказа:</b>\n{items_text}\n\n"
                    f"💰 Сумма: {total_amount}₽\n"
                    f"💸 Итог (после скидок/бонусов): {final_amount}₽\n"
                    f"🔖 Скидки: -{discount_amount}₽  💎 Бонусы: -{bonus_used}₽\n"
                    f"💳 Оплата: {html.escape(str(payment_method))} ({html.escape(str(payment_status))})\n\n"
                )

                admin_text = basic_info + details + "Нажмите кнопку для подтверждения/отклонения."
            else:
                # нет заказа в БД — оставляем базовую информацию
                admin_text = basic_info + "\nНажмите кнопку для подтверждения/отклонения."

            # Дополнительно: подготовим короткую подпись (caption) на случай, если admin_text слишком длинный.
            # Это полезно, если вы отправляете фото с caption (ограничение ~1024 символа в caption по-простому).
            short_caption = None
            try:
                # Попробуем сделать компактную карточку из первых двух позиций
                if order:
                    short_items = item_lines[:2] if item_lines else []
                    short_items_preview = "\n".join(short_items) if short_items else "• состав не указан"
                    short_caption = (
                        f"💳 <b>ПРИНЯТ СКРИН ОПЛАТЫ</b>\n\n"
                        f"#{order_id} — {html.escape(order.get('customer_name') or message.from_user.full_name)}\n"
                        f"{short_items_preview}\n\n"
                        f"Итог: {final_amount}₽ | {html.escape(str(payment_method))} ({html.escape(str(payment_status))})"
                    )
                    # если и это слишком длинно — обрежем
                    if len(_strip_html_tags(short_caption)) > 1000:
                        short_caption = _make_short(short_caption, plain_limit=1000, cut_chars=700)
            except Exception:
                short_caption = None

            # Отправляем админам: используйте ту же функцию notify_admins_about_delivery_order
            # или напишите отдельный цикл получения админов и отправки сообщения
            from src.utils.config import settings
            admin_ids = [int(a.strip()) for a in settings.ADMIN_IDS.split(",")]
            for admin_id in admin_ids:
                try:
                    # отправляем фото + подпись + кнопки
                    await message.bot.send_photo(chat_id=admin_id, photo=file_id, caption=admin_text, parse_mode="HTML", reply_markup=builder.as_markup())
                except Exception as e:
                    logger.error(f"❌ Failed to forward payment proof to admin {admin_id}: {e}")

            await message.answer("✅ Скрин отправлен администратору. Ожидайте подтверждения.", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return

        # Если пришёл текст (например «Я оплатил») — напомним прислать скрин
        if message.text:
            await message.answer("Пожалуйста, пришлите скрин оплаты (фото). Без скрина админ не сможет подтвердить оплату.")
            return

    except Exception as e:
        logger.error(f"❌ Error handling payment proof: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при отправке скрина.")
        await state.clear()





@router.message(DeliveryStates.confirming_order, F.text == "❌ Отменить")
async def cancel_delivery_order(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Отмена заказа доставки"""
    await message.answer(
        "❌ Заказ отменен",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()
    await show_main_menu(message, l10n)

@router.message(DeliveryStates.viewing_cart, F.text == "🗑️ Очистить корзину")
async def clear_cart(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Очистка корзины"""
    await state.update_data(cart=[])
    await message.answer("🗑️ Корзина очищена")
    await state.set_state(DeliveryStates.choosing_category)
    await message.answer("Выберите категорию:", reply_markup=await kb.get_delivery_categories_kb(l10n))

@router.message(DeliveryStates.viewing_cart, F.text == "📋 Продолжить покупки")
async def continue_shopping(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Продолжить покупки"""
    await state.set_state(DeliveryStates.choosing_category)
    await message.answer("Выберите категорию:", reply_markup=await kb.get_delivery_categories_kb(l10n))

# Вспомогательные функции
async def view_cart_from_anywhere(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Показать корзину из любого состояния"""
    data = await state.get_data()
    cart = data.get('cart', [])
    
    if not cart:
        await message.answer("🛒 Корзина пуста")
        return
    
    text = "🛒 <b>ВАША КОРЗИНА</b>\n\n"
    subtotal = 0
    
    for item in cart:
        item_total = item['price'] * item['quantity']
        subtotal += item_total
        text += f"• {item['name']} x{item['quantity']} - {item_total}₽\n"
    
    delivery_cost = 0 if subtotal >= 1500 else 200
    total = subtotal + delivery_cost
    
    text += f"\n💰 <b>Сумма товаров:</b> {subtotal}₽\n"
    
    if delivery_cost > 0:
        text += f"🚗 <b>Доставка:</b> {delivery_cost}₽\n"
    else:
        text += f"🎉 <b>Доставка:</b> бесплатно!\n"
    
    text += f"💵 <b>Итого:</b> {total}₽\n"
    
    if subtotal < 500:
        text += f"\n⚠️ <i>Минимальная сумма заказа 500₽</i>\n"
    
    builder = ReplyKeyboardBuilder()
    if cart:
        builder.button(text="✅ Оформить заказ")
        builder.button(text="📋 Продолжить покупки")
        builder.button(text="🗑️ Очистить корзину")
    builder.button(text="🔙 Главное меню")
    builder.adjust(1)
    
    await state.set_state(DeliveryStates.viewing_cart)
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())



async def notify_admins_about_delivery_order(
    bot,
    order_id: int,
    order_data: dict,
    customer_name: str,
    customer_phone: str,
    total: float,
    delivery_address: str,
    db_manager=None,
    custom_admin_message: str = None
):
    """Уведомление администраторов о новом заказе доставки.

    Улучшения:
    - Явно указывает способ оплаты (payment_method) и статус оплаты, если они есть.
    - При оплате по реквизитам (card/bank_transfer) добавляет кнопки подтверждения/отклонения оплаты.
    - При наличии db_manager пытается получить и переслать админам последние присланные квитанции (payment_receipts).
    - Принимает optional custom_admin_message — если передан, используется вместо стандартного.
    """
    try:
        from src.utils.config import settings
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        # Получаем список админов (защита от пустой строки)
        admin_ids = [int(a.strip()) for a in settings.ADMIN_IDS.split(",") if a.strip()]
        if not admin_ids:
            logger.warning("notify_admins_about_delivery_order: ADMIN_IDS пустой")
            return

        # Состав заказа
        items_text = ""
        items = order_data.get('items', []) if order_data else []
        if items:
            items_text = "<b>Состав заказа:</b>\n"
            for item in items:
                name = item.get('name', '—')
                qty = item.get('quantity', 1)
                price = item.get('price', 0)
                try:
                    line_sum = int(price) * int(qty)
                except Exception:
                    # на случай строк/None
                    try:
                        line_sum = float(price) * float(qty)
                    except Exception:
                        line_sum = 0
                items_text += f"• {name} x{qty} — {line_sum}₽\n"
            items_text += "\n"

        # Определяем способ оплаты и статус
        payment_method_raw = order_data.get('payment_method') if order_data else None
        payment_status = order_data.get('payment_status') if order_data else None

        # Читаем удобочитаемую подпись способа оплаты
        pm_map = {
            'cash': "Наличными курьеру",
            'card': "Оплата по реквизитам / картой (ожидает подтверждения)",
            'bank_transfer': "Перевод на реквизиты / банк (ожидает подтверждения)",
            None: "Не указан"
        }
        payment_method_readable = pm_map.get(payment_method_raw, str(payment_method_raw))

        # Если передан кастомный текст — используем его, иначе формируем стандартный
        if custom_admin_message:
            message_text = custom_admin_message
        else:
            message_text = (
                "🛵 <b>НОВЫЙ ЗАКАЗ ДОСТАВКИ</b>\n\n"
                f"🆔 <b>Номер заказа:</b> #{order_id}\n"
                f"👤 <b>Клиент:</b> {customer_name}\n"
                f"📞 <b>Телефон:</b> {customer_phone}\n"
                f"🏠 <b>Адрес:</b> {delivery_address}\n"
                f"💰 <b>Сумма:</b> {total}₽\n"
                f"💳 <b>Оплата:</b> {payment_method_readable}\n"
            )
            if payment_status:
                message_text += f"📌 <b>Статус оплаты:</b> {payment_status}\n"
            message_text += "\n" + items_text
            message_text += f"⏰ <b>Время доставки:</b> {order_data.get('delivery_time', 'Как можно скорее')}\n\n"
            message_text += "<i>Заказ ожидает обработки</i>"

        # Формируем клавиатуру: базовые кнопки + доп. кнопки для card/bank_transfer (подтвердить/отклонить оплату)
        kb = InlineKeyboardBuilder()

        # Кнопки для подтверждения/отклонения оплаты (только если оплата по реквизитам/карте)
        if payment_method_raw in ('card', 'bank_transfer'):
            kb.button(text="✅ Подтвердить оплату", callback_data=f"payment_confirm_{order_id}")
            kb.button(text="❌ Отклонить оплату", callback_data=f"payment_reject_{order_id}")

        # Стандартные кнопки управления заказом
        kb.button(text="👨‍🍳 В приготовление", callback_data=f"dashboard_start_{order_id}")
        kb.button(text="📞 Позвонить", callback_data=f"dashboard_call_{order_id}")

        # Размещение кнопок: если есть кнопки подтверждения — оставляем по 2 в строке, иначе 1 в строке
        if payment_method_raw in ('card', 'bank_transfer'):
            kb.adjust(2)  # две колонки рекомендованы, т.к. много кнопок
        else:
            kb.adjust(1)

        # Перед отправкой основного сообщения: если есть квитанции в БД — пересылаем их первым (опционально)
        receipts = []
        if db_manager:
            try:
                # Ожидаем, что db_manager реализует get_payment_receipts_for_order(order_id)
                receipts = await db_manager.get_payment_receipts_for_order(order_id)
            except Exception as e:
                logger.debug(f"notify_admins_about_delivery_order: не удалось получить receipts для {order_id}: {e}")

        # Отправляем admin notification (и при наличии — пересылаем фото-квитанции)
        for admin_id in admin_ids:
            try:
                # Если есть receipts — отдельно отправляем их (последние сверху). Отправка фото перед основным текстом
                if receipts:
                    for r in receipts:
                        try:
                            file_id = r.get('file_id') or r.get('fileid') or r.get('file')
                            if file_id:
                                caption = f"💳 Квитанция для заказа #{order_id}\n"
                                # Добавим короткие метаданные, если есть
                                if r.get('note'):
                                    caption += f"{r.get('note')}\n"
                                await bot.send_photo(chat_id=admin_id, photo=file_id, caption=caption)
                        except Exception as e:
                            logger.debug(f"notify_admins_about_delivery_order: failed to send receipt to admin {admin_id}: {e}")

                # Основное сообщение с кнопками
                await bot.send_message(
                    chat_id=admin_id,
                    text=message_text,
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML"
                )

                logger.info(f"✅ Delivery order notification sent to admin {admin_id}")

                if db_manager:
                    # Логируем уведомление админа в user_action (если есть метод add_user_action)
                    try:
                        await db_manager.add_user_action(
                            user_id=admin_id,
                            action_type='delivery_order_notified',
                            action_data={'order_id': order_id, 'payment_method': payment_method_raw}
                        )
                    except Exception:
                        logger.debug("notify_admins_about_delivery_order: add_user_action failed (non-critical)")

            except Exception as e:
                logger.error(f"❌ Failed to notify admin {admin_id} about delivery order {order_id}: {e}")

    except Exception as e:
        logger.error(f"❌ Error in notify_admins_about_delivery_order: {e}", exc_info=True)

async def is_first_order(user_id: int, db_manager) -> bool:
    """Проверяет, является ли заказ первым для пользователя"""
    try:
        # Проверяем заказы доставки
        delivery_orders = await db_manager.get_delivery_orders_by_user(user_id)
        
        # Логируем для отладки
        logger.info(f"🔍 Checking first order for user {user_id}: found {len(delivery_orders)} delivery orders")
        
        # Считаем только завершенные/доставленные заказы как "реальные" заказы
        completed_orders = [order for order in delivery_orders if order['status'] in ['delivered', 'completed']]
        
        logger.info(f"🔍 Completed orders for user {user_id}: {len(completed_orders)}")
        
        return len(completed_orders) == 0  # Если завершенных заказов нет, то это первый
        
    except Exception as e:
        logger.error(f"❌ Error checking first order: {e}")
        return True  # В случае ошибки считаем что это первый заказ
    


async def recalculate_order_after_referral(state: FSMContext, db_manager: DatabaseManager, user_id: int):
    """Пересчет заказа после активации реферального кода"""
    try:
        data = await state.get_data()
        cart = data.get('cart', [])
        
        if not cart:
            return data
            
        # Базовая сумма товаров
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        
        # Расчет доставки
        delivery_cost = 0 if subtotal >= 1500 else 200
        total_before_discount = subtotal + delivery_cost
        
        # Проверяем, есть ли у пользователя реферер и является ли это первый заказ
        user = await db_manager.get_user(user_id)
        discount = 0
        
        logger.info(f"🔍 Recalculating order: user_id={user_id}, has_referrer={user and user.get('referrer_id')}")
        
        if user and user.get('referrer_id'):
            is_first = await is_first_order(user_id, db_manager)
            logger.info(f"🔍 First order check: {is_first}")
            if is_first:
                discount = total_before_discount * 0.10
                logger.info(f"🔍 Applying 10% discount: {discount}₽")
        
        total_after_discount = total_before_discount - discount
        
        # Получаем бонусный баланс
        bonus_balance = await db_manager.get_user_bonus_balance(user_id)
        max_bonus_usage = total_after_discount * 0.6  # Можно использовать до 60% от суммы
        
        # Обновляем данные в состоянии
        await state.update_data(
            subtotal=subtotal,
            delivery_cost=delivery_cost,
            total_before_discount=total_before_discount,
            discount=discount,
            total_after_discount=total_after_discount,
            bonus_balance=bonus_balance,
            max_bonus_usage=max_bonus_usage
        )
        
        logger.info(f"🔢 Recalculated order: subtotal={subtotal}, delivery={delivery_cost}, discount={discount}, total_after_discount={total_after_discount}")
        
        return {
            'subtotal': subtotal,
            'delivery_cost': delivery_cost,
            'total_before_discount': total_before_discount,
            'discount': discount,
            'total_after_discount': total_after_discount,
            'bonus_balance': bonus_balance,
            'max_bonus_usage': max_bonus_usage
        }
        
    except Exception as e:
        logger.error(f"❌ Error recalculating order after referral: {e}")
        return data