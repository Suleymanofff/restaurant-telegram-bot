import asyncio
from datetime import datetime, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FSMCleanupService:
    def __init__(self, storage: BaseStorage, timeout_minutes: int = 30):
        self.storage = storage
        self.timeout_minutes = timeout_minutes
        self.is_running = False
    
    async def start_cleanup_task(self):
        """Запускает фоновую задачу очистки устаревших состояний"""
        self.is_running = True
        while self.is_running:
            try:
                await self.cleanup_expired_states()
                await asyncio.sleep(300)  # Проверяем каждые 5 минут
            except Exception as e:
                logger.error(f"FSM cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def stop_cleanup_task(self):
        """Останавливает задачу очистки"""
        self.is_running = False
    
    async def cleanup_expired_states(self):
        """Очищает устаревшие состояния FSM"""
        try:
            # Эта логика зависит от реализации storage
            # Для памяти: states хранятся в оперативке, очистка не нужна
            # Для Redis/DB: нужно реализовать очистку по TTL
            logger.debug("FSM cleanup check performed")
        except Exception as e:
            logger.error(f"FSM cleanup failed: {e}")

# Глобальный экземпляр
fsm_cleanup_service = None

async def start_fsm_cleanup(storage: BaseStorage):
    """Запуск сервиса очистки FSM"""
    global fsm_cleanup_service
    fsm_cleanup_service = FSMCleanupService(storage)
    asyncio.create_task(fsm_cleanup_service.start_cleanup_task())

async def stop_fsm_cleanup():
    """Остановка сервиса очистки FSM"""
    global fsm_cleanup_service
    if fsm_cleanup_service:
        await fsm_cleanup_service.stop_cleanup_task()