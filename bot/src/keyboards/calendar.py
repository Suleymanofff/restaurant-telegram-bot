from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
from calendar import monthrange

class Calendar:
    @staticmethod
    def get_calendar_keyboard(year: int = None, month: int = None) -> InlineKeyboardMarkup:
        """Генерация интерактивного календаря"""
        now = datetime.now()
        if not year:
            year = now.year
        if not month:
            month = now.month
        
        # Названия месяцев
        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        builder = InlineKeyboardBuilder()
        
        # Заголовок с навигацией
        builder.row(
            InlineKeyboardButton(
                text="←", 
                callback_data=f"calendar_prev_{year}_{month}"
            ),
            InlineKeyboardButton(
                text=f"{month_names[month-1]} {year}", 
                callback_data="ignore"
            ),
            InlineKeyboardButton(
                text="→", 
                callback_data=f"calendar_next_{year}_{month}"
            )
        )
        
        # Дни недели
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        for day in week_days:
            builder.add(InlineKeyboardButton(text=day, callback_data="ignore"))
        
        # Дни месяца
        _, days_in_month = monthrange(year, month)
        first_day_weekday = datetime(year, month, 1).weekday()
        
        # Пустые кнопки для выравнивания
        for _ in range(first_day_weekday):
            builder.add(InlineKeyboardButton(text=" ", callback_data="ignore"))
        
        # Кнопки с днями
        today = datetime.now().date()
        for day in range(1, days_in_month + 1):
            current_date = datetime(year, month, day).date()
            is_past = current_date < today
            is_today = current_date == today
            
            if is_past:
                builder.add(InlineKeyboardButton(
                    text=f"❌{day}", 
                    callback_data="ignore"
                ))
            elif is_today:
                builder.add(InlineKeyboardButton(
                    text=f"📍{day}", 
                    callback_data=f"calendar_select_{year}_{month:02d}_{day:02d}"
                ))
            else:
                builder.add(InlineKeyboardButton(
                    text=str(day), 
                    callback_data=f"calendar_select_{year}_{month:02d}_{day:02d}"
                ))
        
        # Кнопка отмены
        builder.row(
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reservation")
        )
        
        builder.adjust(3, 7, *[7 for _ in range((days_in_month + first_day_weekday - 1) // 7 + 1)], 1)
        return builder.as_markup()

    @staticmethod
    def get_time_keyboard() -> InlineKeyboardMarkup:
        """Генерация клавиатуры для выбора времени"""
        builder = InlineKeyboardBuilder()
        
        # Популярные временные слоты
        time_slots = [
            "10:00", "11:00", "12:00", "13:00", "14:00", "15:00",
            "16:00", "17:00", "18:00", "19:00", "20:00", "21:00"
        ]
        
        for time_slot in time_slots:
            builder.add(InlineKeyboardButton(
                text=time_slot, 
                callback_data=f"time_select_{time_slot}"
            ))
        
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_calendar"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_reservation")
        )
        
        builder.adjust(3, 3, 3, 3, 2)
        return builder.as_markup()