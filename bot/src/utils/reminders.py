import asyncio
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta, date, time
from src.database.db_manager import DatabaseManager
from aiogram import Bot

class ReminderSystem:
    def __init__(self, bot: Bot, db_manager: DatabaseManager):
        self.bot = bot
        self.db_manager = db_manager
        self.is_running = False
        self.sent_reminders_24h = set()
        self.sent_reminders_3h = set()
    
    async def start(self):
        """Запуск системы напоминаний"""
        self.is_running = True
        while self.is_running:
            try:
                # Сначала обновляем прошедшие брони
                await self.db_manager.update_expired_reservations()
                
                # Затем проверяем напоминания
                await self.check_reminders()
                await asyncio.sleep(300)  # Проверяем каждые 5 минут
            except Exception as e:
                print(f"Reminder system error: {e}")
                await asyncio.sleep(60)
    
    async def stop(self):
        """Остановка системы напоминаний"""
        self.is_running = False
    
    async def check_reminders(self):
        """Проверка и отправка напоминаний"""
        now = datetime.now()
        
        # Напоминание за 24 часа
        tomorrow_date = (now + timedelta(days=1)).strftime("%d.%m.%Y")
        tomorrow_reservations = await self.db_manager.get_reservations_for_date(tomorrow_date)
        
        for reservation in tomorrow_reservations:
            if (reservation['status'] == 'confirmed' and 
                reservation['id'] not in self.sent_reminders_24h):
                
                reservation_date = reservation['reservation_date']
                reservation_time = reservation['reservation_time']
                
                if isinstance(reservation_date, date) and isinstance(reservation_time, time):
                    reservation_datetime = datetime.combine(reservation_date, reservation_time)
                    time_until_reservation = reservation_datetime - now
                    
                    # Отправляем напоминание за 23.5-24.5 часа до брони
                    if timedelta(hours=23, minutes=30) <= time_until_reservation <= timedelta(hours=24, minutes=30):
                        await self.send_24h_reminder(reservation)
                        self.sent_reminders_24h.add(reservation['id'])
        
        # Напоминание за 3 часа
        today_date = now.strftime("%d.%m.%Y")
        today_reservations = await self.db_manager.get_reservations_for_date(today_date)
        
        for reservation in today_reservations:
            if (reservation['status'] == 'confirmed' and 
                reservation['id'] not in self.sent_reminders_3h):
                
                reservation_date = reservation['reservation_date']
                reservation_time = reservation['reservation_time']
                
                if isinstance(reservation_date, date) and isinstance(reservation_time, time):
                    reservation_datetime = datetime.combine(reservation_date, reservation_time)
                    time_until_reservation = reservation_datetime - now
                    
                    # Отправляем напоминание за 2.5-3.5 часа до брони
                    if timedelta(hours=2, minutes=30) <= time_until_reservation <= timedelta(hours=3, minutes=30):
                        await self.send_3h_reminder(reservation)
                        self.sent_reminders_3h.add(reservation['id'])
        
        # Очищаем старые записи из кэша напоминаний
        self._cleanup_old_reminders()
    
    def _cleanup_old_reminders(self):
        """Очистка старых напоминаний из кэша"""
        # Удаляем ID броней, которые уже прошли (старше 2 дней)
        current_ids_24h = set()
        current_ids_3h = set()
        
        # В реальном приложении здесь нужно проверять актуальность ID в базе
        # Пока просто ограничим размер множеств
        if len(self.sent_reminders_24h) > 100:
            self.sent_reminders_24h.clear()
        if len(self.sent_reminders_3h) > 100:
            self.sent_reminders_3h.clear()
    
    async def send_24h_reminder(self, reservation):
        """Отправка напоминания за 24 часа"""
        # Форматируем дату для отображения
        reservation_date = reservation['reservation_date']
        if isinstance(reservation_date, date):
            formatted_date = reservation_date.strftime("%d.%m.%Y")
        else:
            formatted_date = str(reservation_date)
        
        # Форматируем время для отображения
        reservation_time = reservation['reservation_time']
        if isinstance(reservation_time, time):
            formatted_time = reservation_time.strftime("%H:%M")
        else:
            formatted_time = str(reservation_time)

        # Создаем клавиатуру с кнопкой отмены
        keyboard = InlineKeyboardBuilder()
        keyboard.button(
            text="❌ Отменить бронь", 
            callback_data=f"cancel_reservation_{reservation['id']}"
        )
        
        message_text = f"""
🔔 <b>Напоминание о бронировании!</b>

Через 24 часа у вас бронь в нашем ресторане.

📅 Дата: {formatted_date}
🕐 Время: {formatted_time}
👥 Гости: {reservation['guests_count']}

Если планы изменились, вы можете отменить бронь:
"""
        
        try:
            await self.bot.send_message(
                reservation['user_id'], 
                message_text, 
                reply_markup=keyboard.as_markup(),
                parse_mode="HTML"  # Добавляем HTML для форматирования
            )
            print(f"📨 Sent 24h reminder for reservation #{reservation['id']} to user {reservation['user_id']}")
        except Exception as e:
            print(f"❌ Failed to send 24h reminder: {e}")
    
    async def send_3h_reminder(self, reservation):
        """Отправка напоминания за 3 часа"""
        # Форматируем дату для отображения
        reservation_date = reservation['reservation_date']
        if isinstance(reservation_date, date):
            formatted_date = reservation_date.strftime("%d.%m.%Y")
        else:
            formatted_date = str(reservation_date)
        
        # Форматируем время для отображения
        reservation_time = reservation['reservation_time']
        if isinstance(reservation_time, time):
            formatted_time = reservation_time.strftime("%H:%M")
        else:
            formatted_time = str(reservation_time)

        # Создаем клавиатуру с кнопкой отмены
        keyboard = InlineKeyboardBuilder()
        keyboard.button(
            text="❌ Отменить бронь", 
            callback_data=f"cancel_reservation_{reservation['id']}"
        )
        
        message_text = f"""
⏰ <b>Скоро встреча!</b>

Через 3 часа у вас бронь в нашем ресторане.

📅 Дата: {formatted_date}
🕐 Время: {formatted_time}
👥 Гости: {reservation['guests_count']}

Если не успеваете, отмените бронь:
"""
        
        try:
            await self.bot.send_message(
                reservation['user_id'],
                message_text, 
                reply_markup=keyboard.as_markup(),
                parse_mode="HTML"  # Добавляем HTML для форматирования
            )
            print(f"📨 Sent 3h reminder for reservation #{reservation['id']} to user {reservation['user_id']}")
        except Exception as e:
            print(f"❌ Failed to send 3h reminder: {e}")

# Глобальный экземпляр системы напоминаний
reminder_system = None

async def start_reminder_system(bot: Bot, db_manager: DatabaseManager):
    """Запуск системы напоминаний"""
    global reminder_system
    reminder_system = ReminderSystem(bot, db_manager)
    asyncio.create_task(reminder_system.start())

async def stop_reminder_system():
    """Остановка системы напоминаний"""
    global reminder_system
    if reminder_system:
        await reminder_system.stop()