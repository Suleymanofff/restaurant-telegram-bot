# src/utils/order_utils.py
import re
from aiogram.utils.keyboard import InlineKeyboardBuilder

def _strip_html_tags(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text)

def caption_too_long(text: str, limit: int = 1024) -> bool:
    return len(_strip_html_tags(text)) > limit

def build_order_dashboard_payload(order: dict):
    # Скопируйте логику из вашего build_order_dashboard_payload (только использующиеся части),
    # но НЕ импортируя ничего из admin.* модулей
    # Верните (text, kb) - InlineKeyboardBuilder или InlineKeyboardMarkup
    kb = InlineKeyboardBuilder()
    # ... (логика формирования items_text и клавиатуры)
    # для краткости покажу пример-скелет:
    order_id = order.get('id')
    text = f"🆕 <b>Заказ #{order_id}</b>\n\n"
    # добавьте остальные поля: items, qty, суммы, оплата
    # build kb buttons как у вас
    return text, kb

def format_order_card(order: dict, urgent: bool = False):
    # Вынесите сюда код форматирования одной карточки (взятый из DeliveryDashboard.format_order_card)
    # Возвращает строку
    ...
