from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluent.runtime import FluentLocalization
import logging

from src.utils.config import settings
from src.utils.logger import get_logger

router = Router()
logger = get_logger(__name__)

@router.message(F.text == "🗺️ Проложить маршрут")
async def get_directions_handler(message: Message, l10n: FluentLocalization, db_manager=None):
    """Расширенный обработчик для построения маршрута"""
    try:
        user = message.from_user
        
        # Логируем действие
        if db_manager:
            await db_manager.add_user_action(
                user_id=user.id,
                action_type='get_directions_click'
            )

        restaurant_address = settings.RESTAURANT_ADDRESS
        latitude = settings.RESTAURANT_LATITUDE
        longitude = settings.RESTAURANT_LONGITUDE

        # Создаем расширенную клавиатуру
        builder = InlineKeyboardBuilder()
        
        # Ссылки для различных карт
        google_maps_url = f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"
        yandex_maps_url = f"https://yandex.ru/maps/?rtext=~{latitude},{longitude}"
        apple_maps_url = f"http://maps.apple.com/?daddr={latitude},{longitude}"
        waze_url = f"https://waze.com/ul?ll={latitude},{longitude}&navigate=yes"
        
        builder.button(text="🗺️ Google Maps", url=google_maps_url)
        builder.button(text="📍 Яндекс.Карты", url=yandex_maps_url)
        builder.button(text="🍎 Apple Maps", url=apple_maps_url)
        builder.button(text="🚗 Waze", url=waze_url)
        # builder.button(text="📞 Позвонить", callback_data="call_restaurant")
        builder.adjust(1)

        # Подробное сообщение с информацией о ресторане
        text = (
            f"🍽️ <b>Добро пожаловать в наш ресторан!</b>\n\n"
            f"📍 <b>Адрес:</b>\n{restaurant_address}\n\n"
            f"🕒 <b>Часы работы:</b>\n"
            f"• Пн-Чт: 10:00 - 23:00\n"
            f"• Пт-Сб: 10:00 - 00:00\n"
            f"• Вс: 10:00 - 22:00\n\n"
            f"📞 <b>Телефон:</b> +7 (495) 123-45-67\n\n"
            f"🚗 <b>Парковка:</b> Есть бесплатная парковка\n"
            f"♿ <b>Доступность:</b> Полностью доступно для маломобильных гостей\n\n"
            f"<b>Выберите способ построения маршрута:</b>"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
        # Дополнительно отправляем локацию
        try:
            await message.answer_location(
                latitude=latitude,
                longitude=longitude,
                title="Наш ресторан",
                address=restaurant_address
            )
        except Exception as location_error:
            logger.warning(f"⚠️ Could not send location: {location_error}")

        logger.info(f"🗺️ Detailed directions requested by user {user.id}")

    except Exception as e:
        logger.error(f"❌ Error in get_directions_handler: {e}")
        await message.answer(
            "❌ Не удалось загрузить информацию о местоположении. "
            "Пожалуйста, свяжитесь с нами по телефону."
        )

@router.callback_query(F.data == "call_restaurant")
async def call_restaurant_handler(callback: CallbackQuery, l10n: FluentLocalization):
    """Обработчик кнопки 'Позвонить'"""
    try:
        await callback.answer("📞 Телефон ресторана: +7 (495) 123-45-67", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Error in call_restaurant_handler: {e}")
        await callback.answer("❌ Ошибка при получении номера телефона")