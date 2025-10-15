__all__ = ("router", )

from aiogram import Router

router = Router()

# Импортируем и включаем роутеры ПОСЛЕ определения router
from .admin import router as admin_router
from .user import router as user_router

router.include_router(admin_router)
router.include_router(user_router)