from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from fluent.runtime import FluentLocalization
from aiogram.fsm.context import FSMContext
from src.utils.config import settings
from aiogram.fsm.state import any_state


import src.handlers.user.keyboards as kb
from src.states.call_stuff import CallStaff
from src.states.greetings import Greeting
from src.utils.logger import get_logger
from src.utils.rate_limiter import staff_call_limit, reservation_limit, menu_view_limit

router = Router()
logger = get_logger(__name__)

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager=None):
    user = message.from_user
    logger.info(
        "👤 /start command from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Обработка реферальных ссылок
        referrer_id = None
        if len(message.text.split()) > 1:
            args = message.text.split()[1]
            if args.startswith('ref_'):
                referral_code = args[4:]  # Убираем 'ref_'
                
                # Находим пользователя по реферальному коду
                referrer = await db_manager.get_user_by_referral_code(referral_code)
                if referrer and referrer['user_id'] != user.id:
                    referrer_id = referrer['user_id']
                    logger.info(f"🎯 Referral detected: {user.id} referred by {referrer_id}")
        
        # Добавляем пользователя в БД
        if db_manager:
            await db_manager.add_user(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                language_code=user.language_code
            )
            
            # Устанавливаем реферера если есть
            if referrer_id:
                success = await db_manager.set_user_referrer(user.id, referrer_id)
                if success:
                    # Добавляем pending бонус (200₽ для реферера после первого заказа)
                    await db_manager.add_referral_bonus(referrer_id, user.id, 200.00)
                    
                    # Уведомляем реферера
                    try:
                        referrer_notification = (
                            f"🎉 <b>У вас новый реферал!</b>\n\n"
                            f"👤 {user.full_name} зарегистрировался по вашей ссылке.\n"
                            f"💰 Вы получите <b>200₽</b> после его первого заказа!"
                        )
                        await message.bot.send_message(
                            chat_id=referrer_id,
                            text=referrer_notification,
                            parse_mode="HTML"
                        )
                    except Exception as notify_error:
                        logger.error(f"❌ Failed to notify referrer: {notify_error}")
            
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='start',
                action_data={'has_referrer': bool(referrer_id), 'referrer_id': referrer_id}
            )

        welcome_text = l10n.format_value("welcome-message")
        who_are_you_text = l10n.format_value("who-are-you")
        keyboard = await kb.get_sex_of_user_kb(l10n)

        # Если это реферал, добавляем специальное сообщение
        if referrer_id:
            welcome_text += "\n\n🎁 <b>Специально для вас: 10% скидка на первый заказ!</b>"

        await message.answer(welcome_text, parse_mode="HTML")
        await message.answer(who_are_you_text, reply_markup=keyboard)
        await state.set_state(Greeting.get_sex)
        logger.info("👤 /start command text shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send /start command message to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

@router.message(Command("menu"))
async def open_main_menu_from_command(message: Message, l10n: FluentLocalization, db_manager = None):
    await show_main_menu(message, l10n, db_manager)

# Общая функция для показа главного меню
async def show_main_menu(message: Message, l10n: FluentLocalization, db_manager=None):
    user = message.from_user
    
    try:
        # Инициализируем переменные прав
        is_admin = False
        is_staff = False
        user_rights = []

        # Проверяем права через базу данных, если db_manager доступен
        if db_manager:
            # Гарантируем существование пользователя в базе
            await db_manager.ensure_user_exists(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name
            )
            
            # Получаем права из базы данных
            is_admin = await db_manager.is_admin(user.id)
            is_staff = await db_manager.is_staff(user.id)
            
            # Логируем действие
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='main_menu_view'
            )
        else:
            # Fallback: используем статическую проверку из settings
            from src.utils.config import settings
            is_admin = settings.is_admin(user.id)
            is_staff = settings.is_staff(user.id)
        
        # Формируем список прав для логирования
        if is_admin:
            user_rights.append("ADMIN")
        if is_staff:
            user_rights.append("STAFF")
        
        logger.info(
            "👤 Open main menu for user: %s (id: %s, rights: %s)", 
            user.full_name, 
            user.id,
            user_rights or "USER"
        )

        # Получаем клавиатуру с проверкой прав
        keyboard = await kb.get_main_menu_keyboard(
            l10n=l10n,
            user_id=user.id,
            db_manager=db_manager
        )
        
        welcome_text = l10n.format_value("main-menu-text")
        
        await message.answer(welcome_text, reply_markup=keyboard)
        logger.info("👤 Main menu shown to user %s", user.id)
        
    except Exception as e:
        logger.error(
            "❌ Failed to send welcome message to user %s: %s",
            user.id, e, exc_info=True
        )
        
        # Fallback: создаем базовую клавиатуру без проверки прав
        try:
            from src.utils.config import settings
            keyboard = await kb.get_main_menu_keyboard(l10n, user.id)
        except Exception:
            # Минимальная клавиатура на случай полного сбоя
            from aiogram.utils.keyboard import ReplyKeyboardBuilder
            builder = ReplyKeyboardBuilder()
            builder.button(text="🍽️ Меню ресторана")
            builder.button(text="💺 Забронировать стол")
            builder.adjust(1, 1)
            keyboard = builder.as_markup(resize_keyboard=True)
        
        await message.answer(
            "Добро пожаловать! Используйте меню ниже:",
            reply_markup=keyboard
        )

############################################################################# - Меню (начало)
@router.message(F.text == "📃 Меню")
async def get_menu(message: Message, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    logger.info(
        "👤 Food menu button from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Логируем действие
        if db_manager:
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='menu_open'
            )

        menu_text = l10n.format_value("menu-title")
        await message.answer(text=menu_text, reply_markup=await kb.menu_food_types(l10n))
        logger.info("👤 Food menu shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send food menu to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

#-----------------------------[Типы блюд]-----------------------------#
#-----------Завтраки
@router.message(F.text == "🍳 Завтраки")
async def breakfasts(message: Message, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    logger.info(
        "👤 Main_menu->Menu->Breakfasts from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Логируем просмотр категории меню
        if db_manager:
            await db_manager.add_menu_view(
                user_id=user.id,
                category='breakfasts'
            )
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='menu_category_view',
                action_data={'category': 'breakfasts'}
            )

        link_to_breakfasts = "https://telegra.ph/ZAVTRAKI-10-04"
        await message.answer(text=link_to_breakfasts)
        logger.info("👤 Main_menu->Menu->Breakfasts shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send Main_menu->Menu->Breakfasts to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

#-----------Горячие блюда
@router.message(F.text == "🍲 Горячее")
async def hot_dishes(message: Message, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    logger.info(
        "👤 Main_menu->Menu->Hot dishes from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Логируем просмотр категории меню
        if db_manager:
            await db_manager.add_menu_view(
                user_id=user.id,
                category='hot_dishes'
            )
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='menu_category_view',
                action_data={'category': 'hot_dishes'}
            )

        link_to_hot_dishes = "https://telegra.ph/GORYACHEE-10-04-2"
        await message.answer(text=link_to_hot_dishes)
        logger.info("👤 Main_menu->Menu->Hot dishes shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send Main_menu->Menu->Hot dishes to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

#-----------Горячие напитки
@router.message(F.text == "☕ Горячие напитки")
async def hot_drinks(message: Message, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    logger.info(
        "👤 Main_menu->Menu->Hot drinks from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Логируем просмотр категории меню
        if db_manager:
            await db_manager.add_menu_view(
                user_id=user.id,
                category='hot_drinks'
            )
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='menu_category_view',
                action_data={'category': 'hot_drinks'}
            )

        link_to_hot_drinks = "https://telegra.ph/GORYACHIE-NAPITKI-10-04"
        await message.answer(text=link_to_hot_drinks)
        logger.info("👤 Main_menu->Menu->Hot drinks shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send Main_menu->Menu->Hot drinks to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

#-----------Холодные напитки
@router.message(F.text == "🍸 Холодные напитки")
async def cold_drinks(message: Message, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    logger.info(
        "👤 Main_menu->Menu->Cold drinks from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Логируем просмотр категории меню
        if db_manager:
            await db_manager.add_menu_view(
                user_id=user.id,
                category='cold_drinks'
            )
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='menu_category_view',
                action_data={'category': 'cold_drinks'}
            )

        link_to_cold_drinks = "https://telegra.ph/HOLODNYE-NAPITKI-10-04"
        await message.answer(text=link_to_cold_drinks)
        logger.info("👤 Main_menu->Menu->Cold drinks shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send Main_menu->Menu->Cold drinks to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

#-----------Десерты
@router.message(F.text == "🍰 Десерты")
async def desserts(message: Message, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    logger.info(
        "👤 Main_menu->Menu->Desserts from user: %s (id: %s, username: %s)", 
        user.full_name, 
        user.id,
        f"@{user.username}" if user.username else "no username"
    )
    
    try:
        # Логируем просмотр категории меню
        if db_manager:
            await db_manager.add_menu_view(
                user_id=user.id,
                category='desserts'
            )
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='menu_category_view',
                action_data={'category': 'desserts'}
            )

        link_to_desserts = "https://telegra.ph/DESERTY-10-04"
        await message.answer(text=link_to_desserts)
        logger.info("👤 Main_menu->Menu->Desserts shown to user %s", message.from_user.id)
    except Exception as e:
        logger.error(
            "❌ Failed to send Main_menu->Menu->Desserts to user %s: %s",
            user.id, e, exc_info=True
        )
        raise

#=====Кнопка "Назад" в главное меню
@router.message(F.text == "🔙 Назад")
async def back_to_main_menu(message: Message, l10n: FluentLocalization, db_manager = None):
    await show_main_menu(message, l10n, db_manager)

############################################################################# - Меню (конец)

############################################################################# - Вызвать персонал (начало)
@router.message(F.text == "👨‍💼 Вызвать персонал")
@staff_call_limit(cooldown=30)  # 1 вызов в 30 секунд
async def call_staff_handler(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager = None):
    user = message.from_user
    
    # Логируем действие
    if db_manager:
        await db_manager.add_user_action(
            user_id=user.id,
            action_type='staff_call_start'
        )

    staff_text = l10n.format_value("call-staff-message")
    await state.set_state(CallStaff.table_number)
    await message.answer(text=staff_text)
    logger.info("👨‍💼 Staff call initiated by user %s", message.from_user.id)

@router.message(CallStaff.table_number)
async def confirm_staff_handler(message: Message, state: FSMContext, l10n: FluentLocalization, db_manager = None, settings = None):
    user = message.from_user
    user_text = message.text.strip()
    
    # Проверяем номер стола
    if not user_text.isdigit():
        text = l10n.format_value("error-enter-table-number")
        await message.answer(text=text)
        return
        
    table_number = int(user_text)
    if table_number < 1 or table_number > 99:
        text = l10n.format_value("error-enter-table-number")
        await message.answer(text=text)
        return

    # Сохраняем вызов персонала в БД со статусом 'pending'
    call_id = None
    if db_manager:
        call_id = await db_manager.add_staff_call(
            user_id=user.id,
            table_number=table_number
        )
        await db_manager.add_user_action(
            user_id=user.id,
            action_type='staff_call_created',
            action_data={'table_number': table_number, 'call_id': call_id}
        )

    if not call_id:
        await message.answer("❌ Ошибка при создании вызова")
        await state.clear()
        return

    # Сохраняем call_id в состоянии для использования в callback
    await state.update_data(call_id=call_id, table_number=table_number)

    staff_text = l10n.format_value(
        "confirm-staff-message",
        {"table-number": message.text}
    )
    await message.answer(text=staff_text, reply_markup=await kb.confirm_staff_message(l10n))
    logger.info("👨‍💼 Staff call created for user %s at table %s", user.id, table_number)
    
    # ✅ НЕ очищаем состояние - ждем callback

############################################################################# - Вызвать персонал (конец)


@router.message(F.text == "🗺️ Проложить маршрут__")
async def get_directions(message: Message, l10n: FluentLocalization, db_manager=None):
    """Обработка кнопки 'Проложить маршрут'"""
    try:
        user = message.from_user
        
        # Логируем действие
        if db_manager:
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='get_directions_click'
            )

        # Получаем настройки ресторана
        restaurant_address = settings.RESTAURANT_ADDRESS
        latitude = settings.RESTAURANT_LATITUDE
        longitude = settings.RESTAURANT_LONGITUDE

        # Создаем инлайн-клавиатуру с кнопками для карт
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        
        # Ссылки для различных карт
        google_maps_url = f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"
        yandex_maps_url = f"https://yandex.ru/maps/?rtext=~{latitude},{longitude}"
        apple_maps_url = f"http://maps.apple.com/?daddr={latitude},{longitude}"
        
        builder.button(text="🗺️ Google Maps", url=google_maps_url)
        builder.button(text="📍 Яндекс.Карты", url=yandex_maps_url)
        builder.button(text="🍎 Apple Maps", url=apple_maps_url)
        builder.adjust(1)

        # Формируем сообщение
        text = (
            f"📍 <b>Наш ресторан</b>\n\n"
            f"🏠 <b>Адрес:</b> {restaurant_address}\n"
            f"🌐 <b>Координаты:</b> {latitude:.5f}, {longitude:.5f}\n\n"
            f"📱 <b>Выберите приложение для построения маршрута:</b>"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
        logger.info(f"🗺️ Directions requested by user {user.id}")

    except Exception as e:
        logger.error(f"❌ Error in get_directions: {e}")
        await message.answer("❌ Произошла ошибка при получении информации о местоположении.")










# # Добавляем хендлеры для других кнопок главного меню
# @router.message(F.text == "💺 Забронировать стол")
# async def make_reservation(message: Message, l10n: FluentLocalization, db_manager = None):
#     # Логируем действие
#     if db_manager:
#         await db_manager.add_user_action(
#             user_id=message.from_user.id,
#             action_type='reservation_start'
#         )
#     await message.answer("Функция бронирования стола в разработке")

# @router.message(F.text == "🛵 Доставка")
# async def delivery(message: Message, l10n: FluentLocalization, db_manager = None):
#     # Логируем действие
#     if db_manager:
#         await db_manager.add_user_action(
#             user_id=message.from_user.id,
#             action_type='delivery_click'
#         )
#     await message.answer("Функция доставки в разработке")

# @router.message(F.text == "👥 Пригласи друга")
# async def invite_friend(message: Message, l10n: FluentLocalization, db_manager = None):
#     # Логируем действие
#     if db_manager:
#         await db_manager.add_user_action(
#             user_id=message.from_user.id,
#             action_type='invite_friend_click'
#         )
#     await message.answer("Функция приглашения друга в разработке")

# @router.message(F.text == "💳 Карта лояльности")
# async def loyalty_program(message: Message, l10n: FluentLocalization, db_manager = None):
#     # Логируем действие
#     if db_manager:
#         await db_manager.add_user_action(
#             user_id=message.from_user.id,
#             action_type='loyalty_program_click'
#         )
#     await message.answer("Функция карты лояльности в разработке")

# @router.message(F.text == "🗺️ Проложить маршрут")
# async def get_directions(message: Message, l10n: FluentLocalization, db_manager = None):
#     # Логируем действие
#     if db_manager:
#         await db_manager.add_user_action(
#             user_id=message.from_user.id,
#             action_type='get_directions_click'
#         )
#     await message.answer("Функция прокладки маршрута в разработке")

# @router.message(Command("help"))
# async def help_handler(message: Message, l10n: FluentLocalization, db_manager = None):
#     user = message.from_user
#     logger.info(
#         "👤 /help command from user: %s (id: %s, username: %s)", 
#         user.full_name, 
#         user.id,
#         f"@{user.username}" if user.username else "no username"
#     )

#     try:
#         # Логируем действие
#         if db_manager:
#             await db_manager.add_user_action(
#                 user_id=user.id,
#                 action_type='help_command'
#             )

#         help_text = l10n.format_value("help-message")
#         await message.answer(help_text)
#         logger.info("✅ /help message sent to user %s", user.id)
#     except Exception as e:
#         logger.error(
#             "❌ Failed to send welcome message to user %s: %s",
#             user.id, e, exc_info=True
#         )
#         raise




@router.message(Command("cancel"), any_state)
async def cancel_any_state(message: Message, state: FSMContext, l10n: FluentLocalization):
    """Отмена любого активного состояния"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нет активных операций для отмены.")
        return
    
    await state.clear()
    
    # Логируем отмену
    logger.info(f"User {message.from_user.id} cancelled operation from state: {current_state}")
    
    # Возвращаем в главное меню
    await show_main_menu(message, l10n)
    
    await message.answer("✅ Операция отменена. Возврат в главное меню.")



@router.message(Command("help"))
async def help_command(message: Message, l10n: FluentLocalization, db_manager=None):
    """Обработчик команды /help с локализацией и разными правами"""
    try:
        user = message.from_user
        user_id = user.id
        
        # Логируем действие
        if db_manager:
            await db_manager.add_user_action(
                user_id=user_id,
                action_type='help_command'
            )

        # Базовый текст для всех пользователей
        help_text = (
            f"{l10n.format_value('help-title')}\n\n"
            f"{l10n.format_value('help-main-commands')}\n\n"
            f"{l10n.format_value('help-additional')}\n\n"
            f"{l10n.format_value('help-commands')}"
        )

        # Добавляем раздел для администраторов
        if settings.is_admin(user_id):
            help_text += f"\n\n{l10n.format_value('help-admin')}"

        # Общая информация для всех
        help_text += (
            f"\n\n{l10n.format_value('help-support')}\n\n"
            f"{l10n.format_value('help-contacts')}"
        )

        await message.answer(help_text, parse_mode="HTML")
        
        logger.info(f"👤 Help command used by user: {user.full_name} (id: {user.id}, admin: {settings.is_admin(user_id)})")
        
    except Exception as e:
        logger.error(f"❌ Error in help command: {e}")
        await message.answer("❌ Произошла ошибка при отображении справки. Попробуйте позже.")


# # Fallback хендлер для неизвестных сообщений
# @router.message()
# async def unknown_message(message: Message, l10n: FluentLocalization, db_manager = None):
#     """Обрабатывает все сообщения, которые не попали в другие хендлеры"""
#     if message.text:
#         logger.info("❓ Unknown message from user %s: %s", message.from_user.id, message.text)
        
#         # Логируем неизвестное действие
#         if db_manager:
#             await db_manager.add_user_action(
#                 user_id=message.from_user.id,
#                 action_type='unknown_message',
#                 action_data={'text': message.text}
#             )
            
#         help_text = "Неизвестная команда. Используйте кнопки меню."
#         await message.answer(help_text)