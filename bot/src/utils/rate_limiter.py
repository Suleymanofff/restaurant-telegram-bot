from functools import wraps
from typing import Dict, Tuple
import time
from aiogram.types import Message, CallbackQuery
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        # Структура: {(user_id, action): [timestamps]}
        self.user_limits: Dict[Tuple[int, str], list] = defaultdict(list)
        self.cleanup_interval = 3600  # 1 час
        self.last_cleanup = time.time()
    
    def check_limit(self, user_id: int, action: str, cooldown: int, max_requests: int = 1) -> Tuple[bool, float]:
        """
        Проверяет лимит для пользователя и действия
        
        Args:
            user_id: ID пользователя
            action: тип действия
            cooldown: время охлаждения в секундах
            max_requests: максимальное количество запросов за период
            
        Returns:
            (is_limited, remaining_time)
        """
        current_time = time.time()
        
        # Периодическая очистка старых записей
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup_old_entries()
            self.last_cleanup = current_time
        
        key = (user_id, action)
        timestamps = self.user_limits[key]
        
        # Удаляем старые временные метки
        timestamps = [ts for ts in timestamps if current_time - ts < cooldown]
        self.user_limits[key] = timestamps
        
        # Проверяем лимит
        if len(timestamps) >= max_requests:
            oldest_timestamp = min(timestamps)
            remaining = cooldown - (current_time - oldest_timestamp)
            return True, max(0, remaining)
        
        # Добавляем текущую временную метку
        timestamps.append(current_time)
        return False, 0
    
    def cleanup_old_entries(self, max_age: int = 86400):  # 24 часа по умолчанию
        """Очищает старые записи (старше max_age секунд)"""
        current_time = time.time()
        keys_to_remove = []
        
        for key, timestamps in self.user_limits.items():
            # Оставляем только свежие временные метки
            fresh_timestamps = [ts for ts in timestamps if current_time - ts < max_age]
            if fresh_timestamps:
                self.user_limits[key] = fresh_timestamps
            else:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.user_limits[key]
        
        if keys_to_remove:
            logger.debug(f"🧹 Очищено {len(keys_to_remove)} старых записей rate limiting")

# Глобальный экземпляр
rate_limiter = RateLimiter()

def rate_limit(cooldown: int = 60, action: str = "default", max_requests: int = 1):
    """
    Декоратор для ограничения частоты запросов
    
    Args:
        cooldown: время охлаждения в секундах
        action: тип действия (для разделения лимитов)
        max_requests: максимальное количество запросов за период
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Извлекаем user_id из аргументов
            user_id = None
            for arg in args:
                if isinstance(arg, (Message, CallbackQuery)):
                    user_id = arg.from_user.id
                    break
            
            if user_id is None:
                logger.warning(f"❌ Не удалось извлечь user_id для rate limiting в {func.__name__}")
                return await func(*args, **kwargs)
            
            # Проверяем лимит
            is_limited, remaining = rate_limiter.check_limit(user_id, action, cooldown, max_requests)
            
            if is_limited:
                remaining_seconds = int(remaining)
                minutes = remaining_seconds // 60
                seconds = remaining_seconds % 60
                
                if minutes > 0:
                    time_text = f"{minutes} мин {seconds} сек"
                else:
                    time_text = f"{seconds} сек"
                
                message_text = f"⏳ Слишком частые запросы. Попробуйте через {time_text}."
                
                logger.info(f"🚫 Rate limit: user {user_id}, action '{action}', wait {remaining_seconds}s")
                
                if isinstance(args[0], Message):
                    await args[0].answer(message_text)
                elif isinstance(args[0], CallbackQuery):
                    await args[0].answer(message_text, show_alert=True)
                return
            
            # Если лимит не превышен - выполняем функцию
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Специализированные декораторы
def staff_call_limit(cooldown: int = 30, max_requests: int = 3):
    """Специальный декоратор для вызовов персонала"""
    return rate_limit(cooldown=cooldown, action="staff_call", max_requests=max_requests)

def reservation_limit(cooldown: int = 30, max_requests: int = 2):
    """Специальный декоратор для бронирований"""
    return rate_limit(cooldown=cooldown, action="reservation_start", max_requests=max_requests)

def menu_view_limit(cooldown: int = 10, max_requests: int = 10):
    """Специальный декоратор для просмотра меню"""
    return rate_limit(cooldown=cooldown, action="menu_view", max_requests=max_requests)