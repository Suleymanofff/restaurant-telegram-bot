import logging
import sys
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

class ColoredFormatter(logging.Formatter):
    """Кастомный форматтер с цветами для консоли"""
    
    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    FORMATS = {
        logging.DEBUG: blue + "🐛 %(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.INFO: grey + "ℹ️  %(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.WARNING: yellow + "⚠️  %(asctime)s - %(name)s - %(levelname)s - %(message)s" + reset,
        logging.ERROR: red + "❌ %(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s" + reset,
        logging.CRITICAL: bold_red + "💥 %(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s" + reset
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO])
        formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
        return formatter.format(record)

class JSONFormatter(logging.Formatter):
    """Форматтер для структурированного JSON логирования"""
    
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
            "message": record.getMessage(),
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data, ensure_ascii=False)

def setup_logging(
    log_level: str = "INFO",
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
    log_format: str = "colored"  # "colored", "json", "simple"
):
    """
    Настройка системы логирования
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_file_logging: Включить запись в файл
        enable_console_logging: Включить вывод в консоль
        log_format: Формат вывода ("colored", "json", "simple")
    """
    
    # Создаем папку для логов
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Получаем корневой логгер
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Очищаем существующие handlers
    logger.handlers.clear()
    
    # Настройка форматера в зависимости от выбранного формата
    if log_format == "json":
        formatter = JSONFormatter()
        console_formatter = JSONFormatter()
    elif log_format == "colored":
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_formatter = ColoredFormatter()
    else:  # simple
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_formatter = formatter
    
    # File Handler с ротацией
    if enable_file_logging:
        file_handler = RotatingFileHandler(
            log_dir / "bot.log",
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Отдельный файл для ошибок
        error_handler = RotatingFileHandler(
            log_dir / "errors.log",
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
    
    # Console Handler
    if enable_console_logging:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # Устанавливаем уровень для сторонних библиотек чтобы уменьшить шум
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    # Логируем старт системы логирования
    logger.info("🚀 Система логирования инициализирована (уровень: %s, формат: %s)", 
                log_level, log_format)

def get_logger(name: str) -> logging.Logger:
    """Получить логгер с указанным именем"""
    return logging.getLogger(name)

# Создаем логгер для этого модуля
logger = get_logger(__name__)