__all__ = ("router", )

from aiogram import Router

router = Router()

# Импортируем и включаем роутеры ПОСЛЕ определения router
from .message import router as message_router
from .callback import router as callback_router
from .reservation import router as reservation_router
from .delivery import router as delivery_router
from .directions import router as directions_router
from .referral import router as referral_router
from .bonus import router as bonus_router

router.include_router(message_router)
router.include_router(callback_router)
router.include_router(reservation_router)
router.include_router(delivery_router)
router.include_router(directions_router)
router.include_router(referral_router)
router.include_router(bonus_router)