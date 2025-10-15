from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import logging
from typing import Callable, Dict, Any, Awaitable

logger = logging.getLogger(__name__)

class FSMMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        state: FSMContext = data.get("state")
        
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(f"FSM error for user {event.from_user.id}: {e}", exc_info=True)
            
            # Очищаем состояние при ошибке
            if state:
                current_state = await state.get_state()
                if current_state:
                    await state.clear()
                    logger.info(f"Cleared FSM state '{current_state}' for user {event.from_user.id} due to error")
            
            # Отправляем сообщение об ошибке пользователю
            error_message = "❌ Произошла ошибка. Пожалуйста, начните заново."
            if isinstance(event, Message):
                await event.answer(error_message)
            elif isinstance(event, CallbackQuery):
                await event.message.answer(error_message)
                await event.answer()  # Закрываем уведомление callback
            
            return None  # Прерываем дальнейшую обработку