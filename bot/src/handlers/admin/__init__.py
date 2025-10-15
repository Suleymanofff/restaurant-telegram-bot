__all__ = ("router", )

from aiogram import Router

router = Router()

# Импортируем и включаем роутеры ПОСЛЕ определения router
from .message import router as message_router
from .callback import router as callback_router
from .reservation_management import router as reservation_router
from .delivery_dashboard import router as delivery_dashboard_router
from .broadcast import router as broadcast_router
from .settings import router as settings_router
from .settings_handlers import router as settings_handlers_router

router.include_router(message_router)
router.include_router(callback_router)
router.include_router(reservation_router)
router.include_router(delivery_dashboard_router)
router.include_router(broadcast_router)
router.include_router(settings_router)
router.include_router(settings_handlers_router)