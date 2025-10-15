from functools import wraps
from aiogram.types import Message, CallbackQuery
from src.utils.config import settings
import logging

logger = logging.getLogger(__name__)

def admin_required(func):
    """Декоратор для проверки прав администратора"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user_id = None
        
        # Извлекаем user_id из разных типов аргументов
        for arg in args:
            if isinstance(arg, Message):
                user_id = arg.from_user.id
                break
            elif isinstance(arg, CallbackQuery):
                user_id = arg.from_user.id
                break
        
        if not user_id or not settings.is_admin(user_id):
            logger.warning(f"❌ Unauthorized admin access attempt by user {user_id}")
            if len(args) > 0:
                if isinstance(args[0], Message):
                    await args[0].answer("❌ Эта команда доступна только администраторам.")
                elif isinstance(args[0], CallbackQuery):
                    await args[0].answer("❌ У вас нет доступа к этой команде.", show_alert=True)
            return
        
        return await func(*args, **kwargs)
    return wrapper

def staff_required(func):
    """Декоратор для проверки прав персонала"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user_id = None
        
        for arg in args:
            if isinstance(arg, Message):
                user_id = arg.from_user.id
                break
            elif isinstance(arg, CallbackQuery):
                user_id = arg.from_user.id
                break
        
        if not user_id or not settings.is_staff(user_id):
            logger.warning(f"❌ Unauthorized staff access attempt by user {user_id}")
            if len(args) > 0:
                if isinstance(args[0], Message):
                    await args[0].answer("❌ У вас нет доступа к этой команде.")
                elif isinstance(args[0], CallbackQuery):
                    await args[0].answer("❌ У вас нет доступа к этой команде.", show_alert=True)
            return
        
        return await func(*args, **kwargs)
    return wrapper