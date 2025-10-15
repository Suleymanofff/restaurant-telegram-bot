import asyncio
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional
import asyncpg
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

class ReservationManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.restaurant_config = {
            'opening_time': time(10, 0),  # 10:00
            'closing_time': time(22, 0),  # 22:00
            'table_capacity': 40,         # Общая вместимость
            'max_tables': 10,             # Количество столов
            'reservation_duration': timedelta(hours=2),  # Длительность брони
            'cleaning_interval': timedelta(minutes=30)   # Время на уборку
        }
    
    async def check_table_availability(self, reservation_date: str, reservation_time: str, guests_count: int) -> Dict[str, any]:
        """Проверка доступности столов с правильной логикой пересечений"""
        try:
            # Преобразуем дату и время
            day, month, year = map(int, reservation_date.split('.'))
            reservation_date_obj = date(year, month, day)
            
            time_parts = reservation_time.split(':')
            hour, minute = map(int, time_parts)
            reservation_time_obj = time(hour, minute)
            target_datetime = datetime(year, month, day, hour, minute)
            
            # Проверка базовых условий
            basic_checks = await self._check_basic_conditions(target_datetime, guests_count)
            if not basic_checks["available"]:
                return basic_checks
            
            # Получаем все брони на эту дату
            reservations = await self._get_reservations_for_date(reservation_date_obj)
            
            # Проверяем доступность с учетом пересечений
            availability = await self._check_availability_with_overlaps(
                target_datetime, guests_count, reservations
            )
            
            return availability
            
        except Exception as e:
            logger.error(f"❌ Error checking table availability: {e}")
            return {"available": False, "reason": "error", "message": str(e)}
    
    async def _check_basic_conditions(self, target_datetime: datetime, guests_count: int) -> Dict[str, any]:
        """Проверка базовых условий (время работы, валидность даты и т.д.)"""
        hour = target_datetime.hour
        
        # Проверка времени работы
        if hour < self.restaurant_config['opening_time'].hour or hour >= self.restaurant_config['closing_time'].hour:
            return {"available": False, "reason": "restaurant_closed"}
        
        # Проверка на прошедшую дату
        if target_datetime < datetime.now():
            return {"available": False, "reason": "past_date"}
        
        # Проверка количества гостей
        if guests_count <= 0 or guests_count > 20:
            return {"available": False, "reason": "invalid_guests_count"}
        
        return {"available": True}
    
    async def _get_reservations_for_date(self, reservation_date: date) -> List[Dict]:
        """Получение всех бронирований на указанную дату"""
        query = """
            SELECT reservation_time, guests_count, status 
            FROM reservations 
            WHERE reservation_date = $1 
            AND status IN ('pending', 'confirmed')
        """
        
        async with self.db_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, reservation_date)
            return [dict(row) for row in rows]
    
    async def _check_availability_with_overlaps(self, target_datetime: datetime, guests_count: int, reservations: List[Dict]) -> Dict[str, any]:
        """Проверка доступности с учетом пересечений временных интервалов"""
        
        # Рассчитываем временной интервал брони
        reservation_start = target_datetime
        reservation_end = reservation_start + self.restaurant_config['reservation_duration']
        
        # Считаем занятые места в пересекающихся интервалах
        overlapping_guests = 0
        overlapping_reservations = 0
        
        for reservation in reservations:
            # Время существующей брони
            existing_time = reservation['reservation_time']
            if isinstance(existing_time, str):
                # Если время в строковом формате
                existing_hour, existing_minute = map(int, existing_time.split(':'))
                existing_start = datetime(
                    target_datetime.year, target_datetime.month, target_datetime.day,
                    existing_hour, existing_minute
                )
            else:
                # Если время в формате time
                existing_start = datetime.combine(target_datetime, existing_time)
            
            existing_end = existing_start + self.restaurant_config['reservation_duration']
            
            # Проверяем пересечение интервалов
            if self._time_intervals_overlap(
                reservation_start, reservation_end,
                existing_start, existing_end
            ):
                overlapping_guests += reservation['guests_count']
                overlapping_reservations += 1
        
        # Проверяем вместимость
        total_guests_during_overlap = overlapping_guests + guests_count
        
        if overlapping_reservations >= self.restaurant_config['max_tables']:
            return {
                "available": False, 
                "reason": "no_tables",
                "details": f"Все {self.restaurant_config['max_tables']} столов заняты в это время"
            }
        
        if total_guests_during_overlap > self.restaurant_config['table_capacity']:
            return {
                "available": False, 
                "reason": "capacity_exceeded",
                "details": f"Превышена вместимость: {total_guests_during_overlap}/{self.restaurant_config['table_capacity']}"
            }
        
        return {
            "available": True,
            "reason": "available",
            "details": {
                "overlapping_reservations": overlapping_reservations,
                "available_tables": self.restaurant_config['max_tables'] - overlapping_reservations,
                "current_guests": overlapping_guests,
                "capacity_after": self.restaurant_config['table_capacity'] - total_guests_during_overlap
            }
        }
    
    def _time_intervals_overlap(self, start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
        """Проверяет пересекаются ли два временных интервала"""
        return (start1 < end2) and (start2 < end1)
    

    @asynccontextmanager
    async def reservation_transaction(self, reservation_date: str, reservation_time: str):
        """Контекстный менеджер для безопасного создания брони"""
        day, month, year = map(int, reservation_date.split('.'))
        reservation_date_obj = date(year, month, day)
        
        async with self.db_manager.pool.acquire() as conn:
            try:
                # Начинаем транзакцию с высоким уровнем изоляции
                async with conn.transaction(isolation='serializable'):
                    # Блокируем таблицу для предотвращения race conditions
                    await conn.execute("LOCK TABLE reservations IN SHARE UPDATE EXCLUSIVE MODE")
                    
                    yield conn
                    
            except asyncpg.SerializationError:
                logger.warning("⚡ Transaction serialization error - retrying might be needed")
                raise
            except Exception as e:
                logger.error(f"❌ Transaction error: {e}")
                raise
    
    async def create_reservation_atomic(self, user_id: int, reservation_date: str, reservation_time: str,
                                      guests_count: int, customer_name: str, customer_phone: str) -> Optional[int]:
        """Атомарное создание брони с проверкой доступности внутри транзакции"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self.reservation_transaction(reservation_date, reservation_time) as conn:
                    # Повторная проверка доступности внутри транзакции
                    availability = await self.check_table_availability(reservation_date, reservation_time, guests_count)
                    
                    if not availability["available"]:
                        logger.warning(f"❌ Reservation no longer available: {availability['reason']}")
                        return None
                    
                    # Создаем бронь
                    reservation_id = await self._create_reservation_in_transaction(
                        conn, user_id, reservation_date, reservation_time, guests_count, customer_name, customer_phone
                    )
                    
                    logger.info(f"✅ Reservation #{reservation_id} created atomically")
                    return reservation_id
                    
            except asyncpg.SerializationError:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 0.1  # Exponential backoff
                    logger.info(f"🔄 Retrying reservation after serialization error (attempt {attempt + 1})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error("❌ Max retries exceeded for reservation")
                    return None
            except Exception as e:
                logger.error(f"❌ Error in atomic reservation: {e}")
                return None
        
        return None
    
    async def _create_reservation_in_transaction(self, conn, user_id: int, reservation_date: str, reservation_time: str,
                                               guests_count: int, customer_name: str, customer_phone: str) -> int:
        """Создание брони внутри транзакции"""
        
        day, month, year = map(int, reservation_date.split('.'))
        reservation_date_obj = date(year, month, day)
        
        time_parts = reservation_time.split(':')
        hour, minute = map(int, time_parts)
        reservation_time_obj = time(hour, minute)
        
        reservation_id = await conn.fetchval('''
            INSERT INTO reservations 
            (user_id, reservation_date, reservation_time, guests_count, customer_name, customer_phone, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending')
            RETURNING id
        ''', user_id, reservation_date_obj, reservation_time_obj, guests_count, customer_name, customer_phone)
        
        return reservation_id