import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from fluent.runtime import FluentLocalization, FluentResourceLoader

# Импорты из вашего проекта
from src.utils.config import settings
from src.utils.logger import setup_logging, get_logger
from src.handlers import router as main_router
from src.database.db_manager import DatabaseManager
from src.utils.reminders import start_reminder_system, stop_reminder_system
from src.utils.rate_limiter import rate_limiter
from src.middlewares.fsm_middleware import FSMMiddleware
from src.utils.fsm_cleanup import start_fsm_cleanup

# Инициализация менеджера базы данных
db_manager = DatabaseManager()

# Инициализация логирования ДО создания логгера
setup_logging(
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
    enable_file_logging=settings.ENABLE_FILE_LOGGING
)

# Получаем логгер
logger = get_logger(__name__)

# Инициализация системы локализации
loader = FluentResourceLoader("src/i18n/{locale}")
l10n = FluentLocalization(["ru"], ["text.ftl", "button.ftl"], loader)

async def init_database():
    """Инициализация базы данных"""
    try:
        logger.info("🗄️ Initializing database connection...")
        
        # Получаем DSN из настроек или используем значение по умолчанию
        dsn = getattr(settings, 'DATABASE_URL', 'postgresql://garun:origami@localhost/restaurant_bot_with_payment')
        
        await db_manager.init_pool(dsn)
        
        # Проверяем соединение
        if await db_manager.health_check():
            logger.info("✅ Database connected successfully")
            return True
        else:
            logger.error("❌ Database health check failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
        return False

async def close_database():
    """Закрытие соединения с базой данных"""
    try:
        await db_manager.close_pool()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing database connection: {e}")


async def cleanup_rate_limits():
    """Периодическая очистка старых записей rate limiting"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        rate_limiter.cleanup_old_entries()
        logger.debug("🧹 Очищены старые записи rate limiting")


async def init_default_admins(db_manager: DatabaseManager):
    """Добавление администраторов из .env в базу данных"""
    try:
        admin_ids = [int(admin_id.strip()) for admin_id in settings.ADMIN_IDS.split(",")]
        staff_ids = [int(staff_id.strip()) for staff_id in settings.STAFF_IDS.split(",")]
        
        for admin_id in admin_ids:
            await db_manager.add_admin(admin_id, "admin", "Default Admin")
            logger.info(f"✅ Added default admin: {admin_id}")
        
        for staff_id in staff_ids:
            await db_manager.add_staff(staff_id, "staff", "Default Staff")
            logger.info(f"✅ Added default staff: {staff_id}")
            
    except Exception as e:
        logger.error(f"❌ Failed to init default admins: {e}")

async def main():
    logger.info("🚀 Starting Restaurant Bot...")
    
    try:
        # Инициализация базы данных
        db_initialized = await init_database()
        if not db_initialized:
            logger.warning("⚠️  Database not initialized, some features may not work")
        else:
            # Добавляем администраторов по умолчанию
            await init_default_admins(db_manager)
        
        # Логируем информацию о боте
        logger.info("🤖 Initializing bot with token: %s...", settings.BOT_TOKEN[:10] + "..." if settings.BOT_TOKEN else "None")
        
        session = AiohttpSession()
        bot = Bot(
            token=settings.BOT_TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode="HTML")
        )

        dp = Dispatcher()

        # 🔥 ДОБАВЛЯЕМ MIDDLEWARE ДЛЯ FSM
        dp.message.middleware(FSMMiddleware())
        dp.callback_query.middleware(FSMMiddleware())
        
        # Передаем l10n и db_manager в диспетчер через work_data
        dp.workflow_data.update({
            "l10n": l10n,
            "db_manager": db_manager,
            "settings": settings
        })
        
        # Регистрируем роутеры
        dp.include_router(main_router)

        # Запускаем систему напоминаний
        await start_reminder_system(bot, db_manager)
        logger.info("🔔 Reminder system started")

        # 🆕 ЗАПУСКАЕМ CLEANUP RATE LIMITING (после создания бота)
        asyncio.create_task(cleanup_rate_limits())
        logger.info("🧹 Rate limiting cleanup task started")

        # 🔥 ЗАПУСКАЕМ FSM CLEANUP SERVICE
        await start_fsm_cleanup(dp.storage)
        logger.info("🧹 FSM cleanup service started")
        
        # Получаем информацию о зарегистрированных хэндлерах
        logger.info("📋 Registered %s routers", len(dp.sub_routers))
        
        logger.info("✅ Bot initialized successfully")
        logger.info("📡 Starting polling...")
        
        await dp.start_polling(bot)
        
    except ValueError as e:
        logger.error("❌ Configuration error: %s", e, exc_info=True)
    except KeyError as e:
        logger.error("❌ Key error: %s", e, exc_info=True)
    except Exception as e:
        logger.critical("💥 Critical error during bot operation: %s", e, exc_info=True)
        raise
    finally:
        logger.info("🛑 Bot stopped")
        await close_database()  # Закрываем соединение с БД
        if 'bot' in locals():
            await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot interrupted by user")
        os.system("cls" if os.name == 'nt' else "clear")
    except Exception as e:
        logger.critical("💥 Fatal error during bot startup: %s", e, exc_info=True)