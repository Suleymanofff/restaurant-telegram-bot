from datetime import date, datetime, time
import pytz
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Часовой пояс ресторана (например, Europe/Moscow для UTC+3/UTC+4)
RESTAURANT_TIMEZONE = pytz.timezone('Europe/Astrakhan')

def get_restaurant_time(dt=None):
    """
    Получить текущее время в часовом поясе ресторана
    Если dt не указан, возвращает текущее время
    """
    if dt is None:
        dt = datetime.now(pytz.utc)
    
    # Если время наивное (без часового пояса), считаем что это UTC
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    
    # Конвертируем в часовой пояс ресторана
    return dt.astimezone(RESTAURANT_TIMEZONE)

def format_restaurant_time(dt=None, format_str='%H:%M:%S'):
    """
    Отформатировать время в часовом поясе ресторана
    """
    restaurant_time = get_restaurant_time(dt)
    return restaurant_time.strftime(format_str)


def parse_reservation_datetime(date_str, time_str):
    """Парсит дату и время из разных форматов в объект datetime"""
    try:
        # Если это уже datetime объект, возвращаем как есть
        if isinstance(date_str, datetime) and isinstance(time_str, (datetime, time)):
            if isinstance(time_str, time):
                return datetime.combine(date_str.date(), time_str)
            return date_str
        
        # Если это date и time объекты
        if isinstance(date_str, date) and isinstance(time_str, time):
            return datetime.combine(date_str, time_str)
        
        # Парсим строковые форматы
        date_str = str(date_str)
        time_str = str(time_str)
        
        # Парсим дату (поддерживаем оба формата: "10.10.2025" и "2025-10-10")
        if '.' in date_str:
            # Формат "день.месяц.год"
            day, month, year = map(int, date_str.split('.'))
        else:
            # Формат "год-месяц-день"
            year, month, day = map(int, date_str.split('-'))
        
        # Парсим время (поддерживаем "10:00" и "10:00:00")
        time_parts = time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        
        return datetime(year, month, day, hour, minute)
        
    except Exception as e:
        logger.error(f"❌ Error parsing reservation datetime: date_str={date_str}, time_str={time_str}, error={e}")
        return None