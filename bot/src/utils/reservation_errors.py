from enum import Enum
from typing import Dict, Any

class ReservationError(Enum):
    RESTAURANT_CLOSED = "restaurant_closed"
    PAST_DATE = "past_date" 
    NO_TABLES = "no_tables"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    INVALID_GUESTS = "invalid_guests_count"
    CONFLICT = "time_conflict"
    SERVICE_UNAVAILABLE = "service_unavailable"

ERROR_MESSAGES = {
    ReservationError.RESTAURANT_CLOSED: {
        "message": "❌ Ресторан закрыт в это время. Мы работаем с 10:00 до 22:00.",
        "user_friendly": True
    },
    ReservationError.PAST_DATE: {
        "message": "❌ Нельзя забронировать стол на прошедшую дату.",
        "user_friendly": True
    },
    ReservationError.NO_TABLES: {
        "message": "❌ К сожалению, на это время нет свободных столов.",
        "user_friendly": True
    },
    ReservationError.CAPACITY_EXCEEDED: {
        "message": "❌ Превышена общая вместимость ресторана на это время.",
        "user_friendly": True
    },
    ReservationError.INVALID_GUESTS: {
        "message": "❌ Количество гостей должно быть от 1 до 20.",
        "user_friendly": True
    },
    ReservationError.CONFLICT: {
        "message": "❌ Это время стало недоступно. Пожалуйста, выберите другое время.",
        "user_friendly": True
    },
    ReservationError.SERVICE_UNAVAILABLE: {
        "message": "❌ Сервис бронирования временно недоступен. Попробуйте позже.",
        "user_friendly": True
    }
}

def get_reservation_error_message(error_type: ReservationError, details: Dict[str, Any] = None) -> str:
    """Получение пользовательского сообщения об ошибке"""
    error_config = ERROR_MESSAGES.get(error_type, {
        "message": "❌ Произошла ошибка при бронировании.",
        "user_friendly": True
    })
    
    message = error_config["message"]
    
    # Добавляем детали если есть
    if details and error_config.get("include_details", False):
        message += f"\n\nДетали: {details}"
    
    return message