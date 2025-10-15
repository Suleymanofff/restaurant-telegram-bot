import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time
import json
import logging
from asyncio import sleep

from src.database.reservation_manager import ReservationManager

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Кастомное исключение для ошибок базы данных"""
    pass

class DatabaseManager:
    def __init__(self):
        self.pool = None
        self.logger = logging.getLogger(__name__)
        self.max_retries = 3
        self.retry_delay = 1
        self.reservation_manager = None

    async def execute_with_retry(self, operation, *args, **kwargs):
        """
        Выполняет операцию с повторными попытками при ошибках соединения
        """
        for attempt in range(self.max_retries):
            try:
                return await operation(*args, **kwargs)
            except (asyncpg.exceptions.ConnectionDoesNotExistError,
                   asyncpg.exceptions.TooManyConnectionsError,
                   asyncpg.exceptions.ConnectionFailureError) as e:
                if attempt == self.max_retries - 1:
                    self.logger.error(f"Database connection failed after {self.max_retries} attempts: {e}")
                    raise DatabaseError(f"Database connection failed: {e}") from e
                
                self.logger.warning(f"Database connection attempt {attempt + 1} failed, retrying...")
                await sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
            except Exception as e:
                self.logger.error(f"Database operation failed: {e}")
                raise DatabaseError(f"Database operation failed: {e}") from e

    async def init_pool(self, dsn: str):
        """Инициализация пула соединений и менеджера бронирований"""
        try:
            self.pool = await asyncpg.create_pool(dsn)
            self.reservation_manager = ReservationManager(self)
            await self.execute_with_retry(self._health_check_impl)
            self.logger.info("✅ Database connection pool created successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to create database connection pool: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}") from e
        
    async def close_pool(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
            self.logger.info("✅ Database connection pool closed")

    async def _health_check_impl(self) -> bool:
        """Реализация проверки здоровья БД"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1

    async def health_check(self) -> bool:
        """Проверка соединения с базой данных с повторными попытками"""
        try:
            return await self.execute_with_retry(self._health_check_impl)
        except Exception as e:
            self.logger.error(f"❌ Database health check failed: {e}")
            return False

    # ==================== USERS ====================
    async def ensure_user_exists(self, user_id: int, username: str = None, full_name: str = None) -> bool:
        """Гарантирует, что пользователь существует в базе"""
        async def _ensure_user_exists():
            async with self.pool.acquire() as conn:
                user_exists = await conn.fetchval(
                    "SELECT 1 FROM users WHERE user_id = $1", 
                    user_id
                )
                
                if not user_exists:
                    # Создаем базовую запись пользователя
                    username = username or "unknown"
                    full_name = full_name or f"User_{user_id}"
                    
                    await conn.execute('''
                        INSERT INTO users (user_id, username, full_name, language_code)
                        VALUES ($1, $2, $3, 'ru')
                        ON CONFLICT (user_id) DO NOTHING
                    ''', user_id, username, full_name)
                    logger.info(f"✅ Auto-created user record for {user_id}")
                
                return True
        
        try:
            return await self.execute_with_retry(_ensure_user_exists)
        except Exception as e:
            logger.error(f"❌ Failed to ensure user exists {user_id}: {e}")
            return False



    async def add_user(self, user_id: int, username: str, full_name: str, 
                      language_code: str = 'ru') -> bool:
        """Добавление нового пользователя с обработкой ошибок"""
        async def _add_user():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO users (user_id, username, full_name, language_code)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    updated_at = CURRENT_TIMESTAMP
                ''', user_id, username, full_name, language_code)
                return True
        
        try:
            return await self.execute_with_retry(_add_user)
        except Exception as e:
            logger.error(f"❌ Failed to add user {user_id}: {e}")
            return False

    async def update_user_profile(self, user_id: int, sex: str, major: str) -> bool:
        """Обновление профиля пользователя (пол и профессия)"""
        async def _update_user_profile():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE users 
                    SET sex = $1, major = $2, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $3
                ''', sex, major, user_id)
                return True
        try:
            return await self.execute_with_retry(_update_user_profile)
        except Exception as e:
            logger.error(f"❌ Failed to update user profile {user_id}: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получение пользователя по ID"""
        async def _get_user():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT * FROM users WHERE user_id = $1
                ''', user_id)
                return dict(row) if row else None
        try:    
            return await self.execute_with_retry(_get_user)
        except Exception as e:
            logger.error(f"❌ Failed to get user {user_id}: {e}")
            return None

    async def get_users_by_segment(self, segment_key: str) -> List[Dict]:
        """Получение пользователей по сегменту"""
        async def _get_users_by_segment():
            async with self.pool.acquire() as conn:
                base_query = "SELECT user_id FROM users WHERE is_blocked = FALSE"
                
                if segment_key == "male":
                    query = f"{base_query} AND sex = 'male'"
                elif segment_key == "female":
                    query = f"{base_query} AND sex = 'female'"
                elif segment_key == "students":
                    query = f"{base_query} AND major = 'student'"
                elif segment_key == "entrepreneurs":
                    query = f"{base_query} AND major = 'entrepreneur'"
                elif segment_key == "employees":
                    query = f"{base_query} AND major = 'hire'"
                elif segment_key == "freelancers":
                    query = f"{base_query} AND major = 'frilans'"
                else:
                    query = base_query  # all users
                
                rows = await conn.fetch(query)
                return [dict(row) for row in rows]
        
        try:
            return await self.execute_with_retry(_get_users_by_segment)
        except Exception as e:
            logger.error(f"❌ Failed to get users by segment {segment_key}: {e}")
            return []

    # ==================== RESERVATIONS ====================
    async def check_table_availability(self, reservation_date: str, reservation_time: str, guests_count: int) -> dict:
        """Проверка доступности столов через ReservationManager"""
        if not self.reservation_manager:
            return {"available": False, "reason": "service_unavailable"}
        
        return await self.reservation_manager.check_table_availability(
            reservation_date, reservation_time, guests_count
        )

    async def create_reservation(self, user_id: int, reservation_date: str, reservation_time: str,
                               guests_count: int, customer_name: str, customer_phone: str) -> int:
        """Создание брони через атомарный метод"""
        if not self.reservation_manager:
            raise DatabaseError("Reservation manager not initialized")
        
        return await self.reservation_manager.create_reservation_atomic(
            user_id, reservation_date, reservation_time, guests_count, customer_name, customer_phone
        )

    async def get_reservations_by_status(self, status: str):
        """Получение актуальных броней по статусу (исключая прошедшие)"""
        async def _get_reservations_by_status():
            query = """
                SELECT * FROM reservations 
                WHERE status = $1 
                AND (reservation_date > CURRENT_DATE 
                    OR (reservation_date = CURRENT_DATE AND reservation_time::time >= CURRENT_TIME))
                ORDER BY created_at DESC
                LIMIT 10
            """
            return await self.pool.fetch(query, status)
        
        try:
            return await self.execute_with_retry(_get_reservations_by_status)
        except Exception as e:
            self.logger.error(f"❌ Failed to get reservations by status: {e}")
            return None


    async def get_today_reservations(self):
        async def _get_today_reservations():
            """Получение актуальных броней на сегодня"""
            query = """
                SELECT * FROM reservations 
                WHERE reservation_date = CURRENT_DATE 
                AND status IN ('pending', 'confirmed')
                AND reservation_time::time >= CURRENT_TIME
                ORDER BY reservation_time
            """
            return await self.pool.fetch(query)
        try:
            return await self.execute_with_retry(_get_today_reservations)
        except Exception as e:
            self.logger.error(f"❌ Failed to get today reservations: {e}")
            return None
            
            

    async def update_reservation_status(self, reservation_id: int, status: str) -> bool:
        """Обновление статуса брони"""
        query = """
            UPDATE reservations 
            SET status = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
        """
        
        try:
            await self.pool.execute(query, status, reservation_id)
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to update reservation status: {e}")
            return False

    async def get_reservation_by_id(self, reservation_id: int):
        """Получение брони по ID"""
        async def _get_reservation_by_id():
            query = "SELECT * FROM reservations WHERE id = $1"
            return await self.pool.fetchrow(query, reservation_id)
        try:
            return await self.execute_with_retry(_get_reservation_by_id)
        except Exception as e:
            self.logger.error(f"❌ Failed to get_reservation_by_id: {e}")
            return None


    async def get_user_reservations(self, user_id: int):
        """Получение броней пользователя"""
        async def _get_user_reservations():
            query = """
                SELECT * FROM reservations 
                WHERE user_id = $1 
                ORDER BY created_at DESC
                LIMIT 10
            """
            return await self.pool.fetch(query, user_id)
        try:
            return await self.execute_with_retry(_get_user_reservations)
        except Exception as e:
            self.logger.error(f"❌ Failed to get_user_reservations: {e}")
            return None

    async def get_reservations_for_date(self, date_str: str) -> List[Dict]:
        """Получение бронирований на указанную дату с полной информацией"""
        try:
            # Преобразуем дату из формата "день.месяц.год" в объект date
            day, month, year = map(int, date_str.split('.'))
            date_obj = date(year, month, day)
            
            query = """
                SELECT 
                    r.*,
                    u.full_name as user_full_name,
                    u.username as user_username
                FROM reservations r
                LEFT JOIN users u ON r.user_id = u.user_id
                WHERE r.reservation_date = $1
                ORDER BY r.reservation_time, r.created_at
            """
            
            rows = await self.pool.fetch(query, date_obj)
            return rows
            
        except Exception as e:
            self.logger.error(f"❌ Error getting reservations for date {date_str}: {e}")
            return []
        
    async def update_expired_reservations(self):
        """Автоматическое обновление статусов прошедших броней"""
        async def _update_expired_reservation():
            query = """
                UPDATE reservations 
                SET status = 'completed'
                WHERE status IN ('pending', 'confirmed')
                AND (reservation_date < CURRENT_DATE 
                    OR (reservation_date = CURRENT_DATE AND reservation_time::time < CURRENT_TIME))
            """
            result = await self.pool.execute(query)
            self.logger.info(f"✅ Updated expired reservations: {result}")
            return True
        try:
            return await self.execute_with_retry(_update_expired_reservation)
        except Exception as e:
            self.logger.error(f"❌ Failed to update expired reservations: {e}")
            return False
        
    async def archive_old_reservations(self, days_old: int = 30):
        """Архивация старых броней (перемещение в отдельную таблицу или удаление)"""
        async def _archive_old_reservations():
            query = """
                DELETE FROM reservations 
                WHERE reservation_date < CURRENT_DATE - ($1 * INTERVAL '1 day')
                AND status IN ('completed', 'cancelled')
            """
            result = await self.pool.execute(query, days_old)
            self.logger.info(f"✅ Archived reservations older than {days_old} days: {result}")
            return True
        try:
            return await self.execute_with_retry(_archive_old_reservations)
        except Exception as e:
            self.logger.error(f"❌ Failed to archive old reservations: {e}")
            return False

    # ==================== STAFF CALLS ====================
    async def add_staff_call(self, user_id: int, table_number: int, notes: str = None) -> Optional[int]:
        """Добавление вызова персонала"""
        async def _add_staff_call():
            async with self.pool.acquire() as conn:
                call_id = await conn.fetchval('''
                    INSERT INTO staff_calls (user_id, table_number, notes)
                    VALUES ($1, $2, $3)
                    RETURNING id
                ''', user_id, table_number, notes)
                return call_id
        try:
            return await self.execute_with_retry(_add_staff_call)
        except Exception as e:
            logger.error(f"❌ Failed to add staff call for user {user_id}: {e}")
            return None

    async def accept_staff_call(self, call_id: int, staff_id: int, staff_name: str) -> bool:
        """Принять вызов официантом - ТОЛЬКО принятие"""
        async def _accept_staff_call():
            async with self.pool.acquire() as conn:
                result = await conn.execute('''
                    UPDATE staff_calls 
                    SET 
                        status = 'accepted',
                        accepted_at = CURRENT_TIMESTAMP,
                        accepted_by_name = $1,
                        accepted_by = $2  -- 👈 Сохраняем ID официанта
                    WHERE id = $3 AND status = 'pending'
                ''', staff_name, staff_id, call_id)
                
                return "UPDATE 1" in result
        try:
            return await self.execute_with_retry(_accept_staff_call)
        except Exception as e:
            logger.error(f"❌ Failed to accept staff call {call_id}: {e}")
            return False

    async def complete_staff_call(self, call_id: int) -> bool:
        """Завершение вызова персонала"""
        async def _complete_staff_call():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE staff_calls 
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND status IN ('pending', 'accepted')
                ''', call_id)
                return True
        try:
            return await self.execute_with_retry(_complete_staff_call)
        except Exception as e:
            logger.error(f"❌ Failed to complete staff call {call_id}: {e}")
            return False

    async def cancel_staff_call(self, call_id: int) -> bool:
        """Отмена вызова персонала"""
        async def _cancel_staff_call():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE staff_calls 
                    SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND status IN ('pending', 'accepted')
                ''', call_id)
                return True
        try:
            return await self.execute_with_retry(_cancel_staff_call)
        except Exception as e:
            logger.error(f"❌ Failed to cancel staff call {call_id}: {e}")
            return False

    async def get_active_staff_calls(self) -> List[Dict]:
        """Получение активных вызовов персонала"""
        async def _get_active_staff_calls():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT sc.*, u.full_name, u.username
                    FROM staff_calls sc
                    JOIN users u ON sc.user_id = u.user_id
                    WHERE sc.status IN ('pending', 'accepted')
                    ORDER BY sc.created_at ASC
                ''')
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_active_staff_calls)
        except Exception as e:
            logger.error(f"❌ Failed to get active staff calls: {e}")
            return []
        
    async def get_staff_call(self, call_id: int) -> Optional[Dict]:
        """Получить информацию о вызове"""
        async def _get_staff_call():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT 
                        sc.*,
                        u.full_name as user_name,
                        u.username as user_username
                    FROM staff_calls sc
                    LEFT JOIN users u ON sc.user_id = u.user_id
                    WHERE sc.id = $1
                ''', call_id)
                
                if row:
                    result = dict(row)
                    logger.info(f"📥 Получен вызов #{call_id}: статус={result.get('status')}, message_ids={result.get('message_ids')}")
                    return result
                else:
                    logger.warning(f"⚠️ Вызов #{call_id} не найден в БД")
                    return None
        try:
            return await self.execute_with_retry(_get_staff_call)
        except Exception as e:
            logger.error(f"❌ Ошибка получения вызова {call_id}: {e}")
            return None

    async def update_call_message_ids(self, call_id: int, message_ids: Dict[int, int]) -> bool:
        """Сохранить ID сообщений для каждого официанта"""
        async def _update_call_message_ids():
            async with self.pool.acquire() as conn:
                result = await conn.execute('''
                    UPDATE staff_calls 
                    SET message_ids = $1
                    WHERE id = $2
                ''', json.dumps(message_ids), call_id)
                
                success = "UPDATE 1" in result
                if success:
                    logger.info(f"✅ Message IDs обновлены для вызова #{call_id}: {message_ids}")
                else:
                    logger.warning(f"⚠️ Не удалось обновить message IDs для вызова #{call_id}. Результат: {result}")
                
                return success
        try:    
            return await self.execute_with_retry(_update_call_message_ids)
        except Exception as e:
            logger.error(f"❌ Ошибка обновления message IDs для вызова {call_id}: {e}")
            return False

    # ==================== USER ACTIONS ====================
    async def add_user_action(self, user_id: int, action_type: str, action_data: Dict = None) -> bool:
        """Безопасное добавление действия пользователя (с проверкой существования пользователя)"""
        async def _add_user_action():
            async with self.pool.acquire() as conn:
                # Сначала проверяем существование пользователя
                user_exists = await conn.fetchval(
                    "SELECT 1 FROM users WHERE user_id = $1", 
                    user_id
                )
                
                if not user_exists:
                    logger.warning(f"⚠️ User {user_id} not found, skipping action logging")
                    return False
                
                # Если пользователь существует, добавляем действие
                await conn.execute('''
                    INSERT INTO user_actions (user_id, action_type, action_data)
                    VALUES ($1, $2, $3)
                ''', user_id, action_type, json.dumps(action_data) if action_data else None)
                return True
        
        try:
            return await self.execute_with_retry(_add_user_action)
        except Exception as e:
            logger.error(f"❌ Failed to add user action for {user_id}: {e}")
            return False

    # ==================== MENU VIEWS ====================
    async def add_menu_view(self, user_id: int, category: str) -> bool:
        """Добавление/обновление просмотра категории меню"""
        async def _add_menu_view():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO menu_views (user_id, category)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id, category) DO UPDATE SET
                    view_count = menu_views.view_count + 1,
                    last_viewed_at = CURRENT_TIMESTAMP
                ''', user_id, category)
                return True
        try:
            return await self.execute_with_retry(_add_menu_view)
        except Exception as e:
            logger.error(f"❌ Failed to add menu view for user {user_id}: {e}")
            return False
        
    
    # ==================== DELIVERY METHODS ====================

    async def get_delivery_categories(self) -> List[Dict]:
        """Получение уникальных категорий доставки"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT DISTINCT category 
                    FROM delivery_menu 
                    WHERE is_available = TRUE
                    ORDER BY category
                ''')
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get delivery categories: {e}")
            return []

    async def get_delivery_menu(self, category: str = None) -> List[Dict]:
        """Получение меню доставки"""
        try:
            async with self.pool.acquire() as conn:
                if category:
                    rows = await conn.fetch('''
                        SELECT * FROM delivery_menu 
                        WHERE category = $1 AND is_available = TRUE
                        ORDER BY name
                    ''', category)
                else:
                    rows = await conn.fetch('''
                        SELECT * FROM delivery_menu 
                        WHERE is_available = TRUE
                        ORDER BY category, name
                    ''')
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get delivery menu: {e}")
            return []

    async def create_delivery_order(self, user_id: int, order_data: Dict, 
                              discount_amount: float = 0, bonus_used: float = 0, 
                              final_amount: float = None) -> Optional[int]:
        """Создание заказа доставки с учетом скидок и бонусов"""
        try:
            if final_amount is None:
                final_amount = order_data['total'] - discount_amount - bonus_used
            
            async with self.pool.acquire() as conn:
                order_id = await conn.fetchval('''
                    INSERT INTO delivery_orders 
                    (user_id, order_data, customer_name, customer_phone, 
                    delivery_address, total_amount, discount_amount, bonus_used, final_amount, delivery_time)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id
                ''', 
                user_id, 
                json.dumps(order_data), 
                order_data['customer_name'],
                order_data['customer_phone'],
                order_data['delivery_address'],
                order_data['total'],  # Исходная сумма
                discount_amount,      # Сумма скидки
                bonus_used,           # Использованные бонусы
                final_amount,         # Итоговая сумма
                order_data.get('delivery_time', 'Как можно скорее'))
                return order_id
        except Exception as e:
            logger.error(f"❌ Failed to create delivery order: {e}")
            return None

    async def get_delivery_orders_by_status(self, status: str) -> List[Dict]:
        """Получение заказов по статусу"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT delivery_orders.*, u.full_name as user_name
                    FROM delivery_orders
                    LEFT JOIN users u ON delivery_orders.user_id = u.user_id
                    WHERE delivery_orders.status = $1
                    ORDER BY delivery_orders.created_at DESC
                ''', status)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get delivery orders: {e}")
            return []

    async def update_delivery_order_status(self, order_id: int, status: str) -> bool:
        """Обновление статуса заказа доставки"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE delivery_orders 
                    SET status = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                ''', status, order_id)
                return True
        except Exception as e:
            logger.error(f"❌ Failed to update delivery order status: {e}")
            return False
        

    async def get_all_delivery_orders(self) -> List[Dict]:
        """Получение всех заказов доставки"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM delivery_orders 
                    ORDER BY created_at DESC
                ''')
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get all delivery orders: {e}")
            return []
        
    async def get_delivery_orders_today(self) -> List[Dict]:
        """Получение заказов за сегодня"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM delivery_orders 
                    WHERE DATE(created_at) = CURRENT_DATE
                    ORDER BY created_at DESC
                ''')
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get today's delivery orders: {e}")
            return []

    async def get_delivery_order_by_id(self, order_id: int) -> Optional[Dict]:
        """Получение заказа по ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT * FROM delivery_orders WHERE id = $1
                ''', order_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Failed to get delivery order {order_id}: {e}")
            return None
        

    async def get_delivery_orders_by_user(self, user_id: int) -> List[Dict]:
        """Получение всех заказов пользователя"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM delivery_orders 
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                ''', user_id)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get user delivery orders: {e}")
            return []
        

    # ==================== BROADCASTS ====================
    async def create_broadcast(self, title: str, message_text: str, target_sex: str = 'all', 
                         target_major: str = 'all', message_type: str = 'text', 
                         image_file_id: str = None) -> Optional[int]:
        """Создание рассылки с поддержкой разных типов контента"""
        async def _create_broadcast():
            async with self.pool.acquire() as conn:
                broadcast_id = await conn.fetchval('''
                    INSERT INTO broadcasts 
                    (title, message_text, target_sex, target_major, message_type, image_file_id, total_count)
                    VALUES ($1, $2, $3, $4, $5, $6, (
                        SELECT COUNT(*) FROM users 
                        WHERE is_blocked = FALSE
                    ))
                    RETURNING id
                ''', title, message_text, target_sex, target_major, message_type, image_file_id)
                return broadcast_id
        
        try:
            return await self.execute_with_retry(_create_broadcast)
        except Exception as e:
            logger.error(f"❌ Failed to create broadcast: {e}")
            return None

    async def update_broadcast_stats(self, broadcast_id: int, sent_count: int) -> bool:
        """Обновление статистики рассылки"""
        async def _update_broadcast_stats():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE broadcasts 
                    SET sent_count = $1, 
                        status = CASE WHEN sent_count >= total_count THEN 'completed' ELSE 'sending' END,
                        sent_at = CASE WHEN sent_count >= total_count THEN CURRENT_TIMESTAMP ELSE sent_at END
                    WHERE id = $2
                ''', sent_count, broadcast_id)
                return True
        
        try:
            return await self.execute_with_retry(_update_broadcast_stats)
        except Exception as e:
            logger.error(f"❌ Failed to update broadcast stats {broadcast_id}: {e}")
            return False

    # ==================== ANALYTICS METHODS ====================
    async def get_general_stats(self) -> Dict[str, Any]:
        """📊 Общая статистика"""
        async def _get_general_stats():
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow('''
                    SELECT 
                        (SELECT COUNT(*) FROM users) as total_users,
                        (SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE) as new_users_today,
                        (SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days') as new_users_week,
                        (SELECT COUNT(DISTINCT user_id) FROM user_actions 
                         WHERE created_at >= CURRENT_DATE - INTERVAL '30 days') as active_users,
                        (SELECT COUNT(*) FROM reservations) as total_reservations,
                        (SELECT COUNT(*) FROM staff_calls) as total_staff_calls,
                        (SELECT COUNT(*) FROM reservations WHERE created_at::date = CURRENT_DATE) as reservations_today
                ''')
                return dict(stats) if stats else {}
        try:
            return await self.execute_with_retry(_get_general_stats)
        except Exception as e:
            logger.error(f"❌ Failed to get general stats: {e}")
            return {}

    async def get_user_demographics(self) -> List[Dict]:
        """👥 Демографика пользователей"""
        async def _get_user_demographics():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT 
                        sex,
                        major,
                        COUNT(*) as count,
                        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM users), 2) as percentage
                    FROM users 
                    WHERE sex IS NOT NULL AND major IS NOT NULL
                    GROUP BY sex, major
                    ORDER BY count DESC
                ''')
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_user_demographics)
        except Exception as e:
            logger.error(f"❌ Failed to get user demographics: {e}")
            return []

    async def get_user_growth(self, days: int = 30) -> List[Dict]:
        """📈 Рост пользователей"""
        async def _get_user_growth():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as new_users,
                        SUM(COUNT(*)) OVER (ORDER BY DATE(created_at)) as total_users
                    FROM users 
                    WHERE created_at >= CURRENT_DATE - $1 * INTERVAL '1 day'
                    GROUP BY DATE(created_at)
                    ORDER BY date
                ''', days)
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_user_growth)
        except Exception as e:
            logger.error(f"❌ Failed to get user growth: {e}")
            return []

    async def get_daily_activity(self, days: int = 7) -> List[Dict]:
        """📈 Активность по дням"""
        async def _get_daily_activity():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as actions_count,
                        COUNT(DISTINCT user_id) as unique_users,
                        action_type
                    FROM user_actions 
                    WHERE created_at >= CURRENT_DATE - $1 * INTERVAL '1 day'
                    GROUP BY DATE(created_at), action_type
                    ORDER BY date DESC, actions_count DESC
                ''', days)
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_daily_activity)
        except Exception as e:
            logger.error(f"❌ Failed to get daily activity: {e}")
            return []

    async def get_target_segments(self) -> Dict[str, Any]:
        """🎯 Целевые сегменты"""
        async def _get_target_segments():
            async with self.pool.acquire() as conn:
                segments = await conn.fetchrow('''
                    SELECT 
                        (SELECT COUNT(*) FROM users WHERE sex = 'male') as male_count,
                        (SELECT COUNT(*) FROM users WHERE sex = 'female') as female_count,
                        (SELECT COUNT(*) FROM users WHERE major = 'student') as students_count,
                        (SELECT COUNT(*) FROM users WHERE major = 'entrepreneur') as entrepreneurs_count,
                        (SELECT COUNT(*) FROM users WHERE major = 'frilans') as freelancers_count,
                        (SELECT COUNT(*) FROM users WHERE major = 'hire') as employees_count,
                        (SELECT COUNT(*) FROM users WHERE sex = 'male' AND major = 'entrepreneur') as male_entrepreneurs,
                        (SELECT COUNT(*) FROM users WHERE sex = 'female' AND major = 'student') as female_students,
                        (SELECT COUNT(*) FROM users WHERE sex = 'male' AND major = 'frilans') as male_freelancers
                ''')
                return dict(segments) if segments else {}
        try:
            return await self.execute_with_retry(_get_target_segments)
        except Exception as e:
            logger.error(f"❌ Failed to get target segments: {e}")
            return {}

    async def get_reservation_stats(self) -> Dict[str, Any]:
        """📋 Статистика бронирований"""
        async def _get_reservation_stats():
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) as total_reservations,
                        COALESCE(AVG(guests_count), 0) as avg_guests,
                        COALESCE(MAX(guests_count), 0) as max_guests,
                        COUNT(*) FILTER (WHERE status = 'confirmed') as confirmed,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending,
                        COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled,
                        COUNT(*) FILTER (WHERE status = 'completed') as completed,
                        COUNT(*) FILTER (WHERE reservation_date = CURRENT_DATE) as today_reservations,
                        MODE() WITHIN GROUP (ORDER BY EXTRACT(DOW FROM reservation_date)) as most_popular_day
                    FROM reservations
                ''')
                return dict(stats) if stats else {}
        try:
            return await self.execute_with_retry(_get_reservation_stats)
        except Exception as e:
            logger.error(f"❌ Failed to get reservation stats: {e}")
            return {}

    async def get_reservation_trends(self, days: int = 30) -> List[Dict]:
        """📈 Тренды бронирований"""
        async def _get_reservation_trends():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT 
                        reservation_date as date,
                        COUNT(*) as reservations_count,
                        AVG(guests_count) as avg_guests,
                        SUM(guests_count) as total_guests
                    FROM reservations 
                    WHERE reservation_date >= CURRENT_DATE - $1 * INTERVAL '1 day'
                    GROUP BY reservation_date
                    ORDER BY date DESC
                ''', days)
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_reservation_trends)
        except Exception as e:
            logger.error(f"❌ Failed to get reservation trends: {e}")
            return []

    async def get_staff_calls_stats(self) -> Dict[str, Any]:
        """👨‍💼 Статистика вызовов персонала"""
        async def _get_staff_calls_stats():
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow('''
                    SELECT 
                        COUNT(*) as total_calls,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending_calls,
                        COUNT(*) FILTER (WHERE status = 'accepted') as accepted_calls,
                        COUNT(*) FILTER (WHERE status = 'completed') as completed_calls,
                        COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled_calls,
                        COALESCE(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/60) FILTER 
                            (WHERE completed_at IS NOT NULL), 0) as avg_completion_time_min,
                        MODE() WITHIN GROUP (ORDER BY table_number) as most_active_table,
                        COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) as today_calls
                    FROM staff_calls
                ''')
                return dict(stats) if stats else {}
        try:
            return await self.execute_with_retry(_get_staff_calls_stats)    
        except Exception as e:
            logger.error(f"❌ Failed to get staff calls stats: {e}")
            return {}

    async def get_popular_menu_categories(self) -> List[Dict]:
        """📊 Популярные категории меню"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT 
                        category,
                        SUM(view_count) as total_views,
                        COUNT(DISTINCT user_id) as unique_viewers,
                        MAX(last_viewed_at) as last_viewed
                    FROM menu_views 
                    GROUP BY category
                    ORDER BY total_views DESC
                    LIMIT 10
                ''')
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Failed to get popular menu categories: {e}")
            return []
        

        # ==================== REFERRAL METHODS ====================

    async def generate_referral_code(self, user_id: int) -> str:
        """Генерация уникального реферального кода"""
        async def _generate_referral_code():
            async with self.pool.acquire() as conn:
                # Пытаемся использовать username + user_id для создания кода
                user = await self.get_user(user_id)
                base_code = ""
                if user and user.get('username'):
                    base_code = user['username'].upper()[:8]
                else:
                    base_code = "REF"
                
                # Добавляем последние 4 цифры user_id
                code_suffix = str(user_id)[-4:]
                referral_code = f"{base_code}{code_suffix}"
                
                # Проверяем уникальность и при необходимости модифицируем
                counter = 0
                original_code = referral_code
                
                while counter < 10:  # Максимум 10 попыток
                    existing = await conn.fetchval(
                        "SELECT user_id FROM users WHERE referral_code = $1", 
                        referral_code
                    )
                    if not existing:
                        break
                    # Если код уже существует, добавляем случайный символ
                    import random
                    import string
                    referral_code = original_code + random.choice(string.ascii_uppercase)
                    counter += 1
                else:
                    # Если все попытки исчерпаны, используем user_id
                    referral_code = f"REF{user_id}"
                
                # Сохраняем код в БД
                await conn.execute(
                    "UPDATE users SET referral_code = $1 WHERE user_id = $2",
                    referral_code, user_id
                )
                
                return referral_code
        
        try:
            return await self.execute_with_retry(_generate_referral_code)
        except Exception as e:
            logger.error(f"❌ Failed to generate referral code for user {user_id}: {e}")
            return f"REF{user_id}"

    async def get_referral_code(self, user_id: int) -> str:
        """Получение реферального кода пользователя (генерирует если нет)"""
        async def _get_referral_code():
            async with self.pool.acquire() as conn:
                # Проверяем есть ли уже код
                existing_code = await conn.fetchval(
                    "SELECT referral_code FROM users WHERE user_id = $1",
                    user_id
                )
                
                if existing_code:
                    return existing_code
                else:
                    # Генерируем новый код
                    return await self.generate_referral_code(user_id)
        
        try:
            return await self.execute_with_retry(_get_referral_code)
        except Exception as e:
            logger.error(f"❌ Failed to get referral code for user {user_id}: {e}")
            return f"REF{user_id}"

    async def get_user_by_referral_code(self, referral_code: str) -> Optional[Dict]:
        """Получение пользователя по реферальному коду"""
        async def _get_user_by_referral_code():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE referral_code = $1",
                    referral_code.upper()
                )
                return dict(row) if row else None
        
        try:
            return await self.execute_with_retry(_get_user_by_referral_code)
        except Exception as e:
            logger.error(f"❌ Failed to get user by referral code {referral_code}: {e}")
            return None

    async def set_user_referrer(self, user_id: int, referrer_id: int) -> bool:
        """Установка реферера для пользователя с АТОМАРНОЙ проверкой"""
        async def _set_user_referrer():
            async with self.pool.acquire() as conn:
                # АТОМАРНАЯ проверка и установка в одной транзакции
                current_referrer = await conn.fetchval(
                    "SELECT referrer_id FROM users WHERE user_id = $1",
                    user_id
                )
                
                if current_referrer:
                    logger.warning(f"⚠️ User {user_id} already has referrer {current_referrer}")
                    return False
                
                # Устанавливаем реферера
                await conn.execute(
                    "UPDATE users SET referrer_id = $1 WHERE user_id = $2",
                    referrer_id, user_id
                )
                
                # Увеличиваем счетчик рефералов у реферера
                await conn.execute(
                    "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = $1",
                    referrer_id
                )
                
                logger.info(f"✅ Set referrer {referrer_id} for user {user_id}")
                return True
        
        try:
            return await self.execute_with_retry(_set_user_referrer)
        except Exception as e:
            logger.error(f"❌ Failed to set referrer for user {user_id}: {e}")
            return False

    async def add_referral_bonus(self, referrer_id: int, referred_id: int, bonus_amount: float) -> bool:
        """Добавление реферального бонуса"""
        async def _add_referral_bonus():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO referral_bonuses (referrer_id, referred_id, bonus_amount, status)
                    VALUES ($1, $2, $3, 'pending')
                ''', referrer_id, referred_id, bonus_amount)
                return True
        
        try:
            return await self.execute_with_retry(_add_referral_bonus)
        except Exception as e:
            logger.error(f"❌ Failed to add referral bonus: {e}")
            return False

    async def complete_referral_bonus(self, referred_id: int, order_id: int) -> bool:
        """Завершение реферального бонуса после успешного заказа - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        async def _complete_referral_bonus():
            async with self.pool.acquire() as conn:
                # АТОМАРНО находим и обновляем бонус в одной транзакции
                bonus = await conn.fetchrow('''
                    UPDATE referral_bonuses 
                    SET status = 'completed', 
                        completed_at = CURRENT_TIMESTAMP, 
                        order_id = $1
                    WHERE referred_id = $2 
                        AND status = 'pending'
                    RETURNING id, referrer_id, bonus_amount
                ''', order_id, referred_id)
                
                if not bonus:
                    logger.warning(f"⚠️ No pending referral bonus found for referred_id {referred_id}")
                    return False
                
                # Проверяем, не начислялся ли уже бонус за этот заказ
                existing_bonus = await conn.fetchval(
                    "SELECT 1 FROM bonus_transactions WHERE order_id = $1 AND type = 'referral'",
                    order_id
                )
                
                if existing_bonus:
                    logger.warning(f"⚠️ Referral bonus already awarded for order {order_id}")
                    return False
                
                # Начисляем бонус рефереру на баланс
                bonus_amount = bonus['bonus_amount']
                await conn.execute('''
                    UPDATE users 
                    SET total_referral_bonus = total_referral_bonus + $1,
                        bonus_balance = bonus_balance + $1
                    WHERE user_id = $2
                ''', bonus_amount, bonus['referrer_id'])
                
                # Добавляем запись в бонусные транзакции
                await conn.execute('''
                    INSERT INTO bonus_transactions 
                    (user_id, order_id, amount, type, description)
                    VALUES ($1, $2, $3, 'referral', $4)
                ''', bonus['referrer_id'], order_id, bonus_amount, 
                    f'Реферальный бонус за пользователя {referred_id}')
                
                logger.info(f"✅ Completed referral bonus: referrer {bonus['referrer_id']}, amount: {bonus_amount}, order: {order_id}")
                return True
        
        try:
            return await self.execute_with_retry(_complete_referral_bonus)
        except Exception as e:
            logger.error(f"❌ Failed to complete referral bonus: {e}")
            return False

    async def get_referral_stats(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики по реферальной программе"""
        async def _get_referral_stats():
            async with self.pool.acquire() as conn:
                stats = await conn.fetchrow('''
                    SELECT 
                        referral_count as total_referrals,
                        total_referral_bonus,
                        (SELECT COUNT(*) FROM referral_bonuses 
                        WHERE referrer_id = $1 AND status = 'completed') as completed_referrals,
                        (SELECT COUNT(*) FROM referral_bonuses 
                        WHERE referrer_id = $1 AND status = 'pending') as pending_referrals
                    FROM users 
                    WHERE user_id = $1
                ''', user_id)
                
                return dict(stats) if stats else {
                    'total_referrals': 0,
                    'total_referral_bonus': 0,
                    'completed_referrals': 0,
                    'pending_referrals': 0
                }
        
        try:
            return await self.execute_with_retry(_get_referral_stats)
        except Exception as e:
            logger.error(f"❌ Failed to get referral stats for user {user_id}: {e}")
            return {
                'total_referrals': 0,
                'total_referral_bonus': 0,
                'completed_referrals': 0,
                'pending_referrals': 0
            }
        

    async def get_loyalty_card_info(self, user_id: int) -> Dict:
        """Получение информации для карты лояльности"""
        try:
            async with self.pool.acquire() as conn:
                # Получаем баланс пользователя
                balance = await conn.fetchval(
                    "SELECT bonus_balance FROM users WHERE user_id = $1",
                    user_id
                ) or 0.0
                
                # Получаем статистику по транзакциям
                stats_row = await conn.fetchrow('''
                    SELECT 
                        COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as earned,
                        COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spent,
                        COUNT(DISTINCT order_id) as total_orders
                    FROM bonus_transactions 
                    WHERE user_id = $1
                ''', user_id)
                
                # Получаем последние транзакции
                transactions = await conn.fetch('''
                    SELECT amount, description, created_at, type
                    FROM bonus_transactions 
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT 5
                ''', user_id)
                
                return {
                    'balance': float(balance),
                    'stats': {
                        'earned': float(stats_row['earned']) if stats_row else 0.0,
                        'spent': float(stats_row['spent']) if stats_row else 0.0,
                        'total_orders': stats_row['total_orders'] if stats_row else 0
                    },
                    'transactions': [dict(transaction) for transaction in transactions]
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error getting loyalty card info: {e}")
            return {
                'balance': 0.0,
                'stats': {'earned': 0.0, 'spent': 0.0, 'total_orders': 0},
                'transactions': []
            }


    # ==================== BONUS BALANCE METHODS ====================

    async def get_user_bonus_balance(self, user_id: int) -> float:
        """Получение бонусного баланса пользователя"""
        async def _get_user_bonus_balance():
            async with self.pool.acquire() as conn:
                balance = await conn.fetchval(
                    "SELECT bonus_balance FROM users WHERE user_id = $1",
                    user_id
                )
                return float(balance) if balance else 0.0
        
        try:
            return await self.execute_with_retry(_get_user_bonus_balance)
        except Exception as e:
            logger.error(f"❌ Failed to get bonus balance for user {user_id}: {e}")
            return 0.0

    async def update_user_bonus_balance(self, user_id: int, amount: float) -> bool:
        """Обновление бонусного баланса пользователя"""
        async def _update_user_bonus_balance():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET bonus_balance = bonus_balance + $1 WHERE user_id = $2",
                    amount, user_id
                )
                return True
        
        try:
            return await self.execute_with_retry(_update_user_bonus_balance)
        except Exception as e:
            logger.error(f"❌ Failed to update bonus balance for user {user_id}: {e}")
            return False

    async def get_user_referral_discount_eligible(self, user_id: int) -> bool:
        """Проверка, имеет ли пользователь право на скидку по реферальной программе"""
        async def _get_user_referral_discount_eligible():
            async with self.pool.acquire() as conn:
                # Проверяем, есть ли у пользователя реферер И это его первый заказ
                user = await self.get_user(user_id)
                if not user or not user.get('referrer_id'):
                    return False
                
                # Проверяем, есть ли уже завершенные заказы у пользователя
                orders_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM delivery_orders WHERE user_id = $1 AND status = 'delivered'",
                    user_id
                )
                
                return orders_count == 0  # Скидка только на первый заказ
        
        try:
            return await self.execute_with_retry(_get_user_referral_discount_eligible)
        except Exception as e:
            logger.error(f"❌ Failed to check referral discount eligibility for user {user_id}: {e}")
            return False
        

    # ==================== BONUS SYSTEM METHODS ====================
    
    async def add_bonus_transaction(self, user_id: int, amount: float, transaction_type: str, 
                                description: str = None, order_id: int = None) -> bool:
        """Добавление бонусной транзакции"""
        async def _add_bonus_transaction():
            async with self.pool.acquire() as conn:
                # Добавляем транзакцию
                await conn.execute('''
                    INSERT INTO bonus_transactions (user_id, order_id, amount, type, description)
                    VALUES ($1, $2, $3, $4, $5)
                ''', user_id, order_id, amount, transaction_type, description)
                
                # Обновляем баланс пользователя
                await conn.execute('''
                    UPDATE users 
                    SET bonus_balance = bonus_balance + $1
                    WHERE user_id = $2
                ''', amount, user_id)
                return True
        
        try:
            return await self.execute_with_retry(_add_bonus_transaction)
        except Exception as e:
            logger.error(f"❌ Failed to add bonus transaction: {e}")
            return False

    async def get_bonus_transactions(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получение истории бонусных транзакций"""
        async def _get_bonus_transactions():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM bonus_transactions 
                    WHERE user_id = $1 
                    ORDER BY created_at DESC 
                    LIMIT $2
                ''', user_id, limit)
                return [dict(row) for row in rows]
        
        try:
            return await self.execute_with_retry(_get_bonus_transactions)
        except Exception as e:
            logger.error(f"❌ Failed to get bonus transactions: {e}")
            return []

    async def calculate_order_cashback(self, order_amount: float) -> float:
        """Расчет кешбэка для заказа (5%)"""
        return round(order_amount * 0.05, 2)

    async def get_max_bonus_usage(self, order_amount: float) -> float:
        """Максимальное количество бонусов для списания (50% от заказа)"""
        return round(order_amount * 0.5, 2)
    


    async def get_blocked_users(self) -> List[Dict]:
        """Получение списка заблокированных пользователей"""
        async def _get_blocked_users():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT user_id, username, full_name, created_at 
                    FROM users 
                    WHERE is_blocked = TRUE
                    ORDER BY created_at DESC
                ''')
                return [dict(row) for row in rows]
        
        try:
            return await self.execute_with_retry(_get_blocked_users)
        except Exception as e:
            logger.error(f"❌ Failed to get blocked users: {e}")
            return []

    async def block_user(self, user_id: int) -> bool:
        """Блокировка пользователя"""
        async def _block_user():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE users 
                    SET is_blocked = TRUE 
                    WHERE user_id = $1
                ''', user_id)
                return True
        
        try:
            return await self.execute_with_retry(_block_user)
        except Exception as e:
            logger.error(f"❌ Failed to block user {user_id}: {e}")
            return False

    async def unblock_user(self, user_id: int) -> bool:
        """Разблокировка пользователя"""
        async def _unblock_user():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE users 
                    SET is_blocked = FALSE 
                    WHERE user_id = $1
                ''', user_id)
                return True
        
        try:
            return await self.execute_with_retry(_unblock_user)
        except Exception as e:
            logger.error(f"❌ Failed to unblock user {user_id}: {e}")
            return False




    # ==================== ADMIN/STAFF MANAGEMENT ====================

    async def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        async def _is_admin():
            async with self.pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT 1 FROM admin_users WHERE user_id = $1",
                    user_id
                )
                return exists is not None
        try:
            return await self.execute_with_retry(_is_admin)
        except Exception as e:
            logger.error(f"❌ Error checking admin status: {e}")
            return False

    async def is_staff(self, user_id: int) -> bool:
        """Проверка, является ли пользователь персоналом"""
        async def _is_staff():
            async with self.pool.acquire() as conn:
                # Персонал = админы + официанты
                exists = await conn.fetchval('''
                    SELECT 1 FROM (
                        SELECT user_id FROM admin_users 
                        UNION 
                        SELECT user_id FROM staff_users
                    ) AS staff WHERE user_id = $1
                ''', user_id)
                return exists is not None
        try:
            return await self.execute_with_retry(_is_staff)
        except Exception as e:
            logger.error(f"❌ Error checking staff status: {e}")
            return False

    async def add_admin(self, user_id: int, username: str, full_name: str) -> bool:
        """Добавление администратора"""
        async def _add_admin():
            async with self.pool.acquire() as conn:
                # Сначала убедимся, что пользователь существует в users
                await self.ensure_user_exists(user_id, username, full_name)
                
                await conn.execute('''
                    INSERT INTO admin_users (user_id, username, full_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name
                ''', user_id, username, full_name)
                return True
        try:
            return await self.execute_with_retry(_add_admin)
        except Exception as e:
            logger.error(f"❌ Error adding admin: {e}")
            return False

    async def remove_admin(self, user_id: int) -> bool:
        """Удаление администратора"""
        async def _remove_admin():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM admin_users WHERE user_id = $1",
                    user_id
                )
                return True
        try:
            return await self.execute_with_retry(_remove_admin)
        except Exception as e:
            logger.error(f"❌ Error removing admin: {e}")
            return False

    async def get_admins(self) -> List[Dict]:
        """Получение списка администраторов"""
        async def _get_admins():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM admin_users ORDER BY created_at
                ''')
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_admins)
        except Exception as e:
            logger.error(f"❌ Error getting admins: {e}")
            return []

    async def add_staff(self, user_id: int, username: str, full_name: str) -> bool:
        """Добавление официанта"""
        async def _add_staff():
            async with self.pool.acquire() as conn:
                # Сначала убедимся, что пользователь существует в users
                await self.ensure_user_exists(user_id, username, full_name)
                
                await conn.execute('''
                    INSERT INTO staff_users (user_id, username, full_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name
                ''', user_id, username, full_name)
                return True
        try:
            return await self.execute_with_retry(_add_staff)
        except Exception as e:
            logger.error(f"❌ Error adding staff: {e}")
            return False

    async def remove_staff(self, user_id: int) -> bool:
        """Удаление официанта"""
        async def _remove_staff():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM staff_users WHERE user_id = $1",
                    user_id
                )
                return True
        try:
            return await self.execute_with_retry(_remove_staff)
        except Exception as e:
            logger.error(f"❌ Error removing staff: {e}")
            return False

    async def get_staff(self) -> List[Dict]:
        """Получение списка официантов"""
        async def _get_staff():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM staff_users ORDER BY created_at
                ''')
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_staff)
        except Exception as e:
            logger.error(f"❌ Error getting staff: {e}")
            return []

    async def add_dish_to_menu(self, category: str, name: str, description: str, price: float, image_url: str = None) -> bool:
        """Добавление блюда в меню"""
        async def _add_dish_to_menu():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO delivery_menu (category, name, description, price, image_url)
                    VALUES ($1, $2, $3, $4, $5)
                ''', category, name, description, price, image_url)
                return True
        try:
            return await self.execute_with_retry(_add_dish_to_menu)
        except Exception as e:
            logger.error(f"❌ Error adding dish to menu: {e}")
            return False

    async def remove_dish_from_menu(self, dish_id: int) -> bool:
        """Удаление блюда из меню"""
        async def _remove_dish_from_menu():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM delivery_menu WHERE id = $1",
                    dish_id
                )
                return True
        try:
            return await self.execute_with_retry(_remove_dish_from_menu)
        except Exception as e:
            logger.error(f"❌ Error removing dish from menu: {e}")
            return False

    async def get_blocked_users(self) -> List[Dict]:
        """Получение списка заблокированных пользователей"""
        async def _get_blocked_users():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT user_id, username, full_name, created_at 
                    FROM users 
                    WHERE is_blocked = TRUE
                    ORDER BY created_at DESC
                ''')
                return [dict(row) for row in rows]
        try:
            return await self.execute_with_retry(_get_blocked_users)
        except Exception as e:
            logger.error(f"❌ Error getting blocked users: {e}")
            return []
        


    # ==================== PAYMENT METHODS ====================

    async def update_order_payment_method(self, order_id: int, payment_method: str) -> bool:
        """Обновление способа оплаты для заказа"""
        async def _update_order_payment_method():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    UPDATE delivery_orders 
                    SET payment_method = $1 
                    WHERE id = $2
                ''', payment_method, order_id)
                return True
        
        try:
            return await self.execute_with_retry(_update_order_payment_method)
        except Exception as e:
            logger.error(f"❌ Failed to update payment method: {e}")
            return False

    async def confirm_payment(self, order_id: int, confirmed_by: int = None) -> bool:
        async def _fn():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    UPDATE delivery_orders
                    SET payment_status = 'confirmed',
                        status = 'preparing',
                        payment_confirmed_by = $2,
                        payment_confirmed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1 AND (payment_status IS DISTINCT FROM 'confirmed')
                    RETURNING id
                """, order_id, confirmed_by)
                return bool(row)
        return await self.execute_with_retry(_fn)

    async def get_orders_with_pending_payment(self) -> List[Dict]:
        """Получение заказов, ожидающих подтверждения оплаты"""
        async def _get_orders_with_pending_payment():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM delivery_orders 
                    WHERE payment_status = 'pending'
                    AND status NOT IN ('cancelled', 'delivered')
                    ORDER BY created_at DESC
                ''')
                return [dict(row) for row in rows]
        
        try:
            return await self.execute_with_retry(_get_orders_with_pending_payment)
        except Exception as e:
            logger.error(f"❌ Failed to get pending payment orders: {e}")
            return []
        
    async def save_payment_receipt(self, order_id: int, user_id: int, file_id: str, note: str = None) -> bool:
        """Сохранить информацию о присланном платёжном документе/скрине"""
        async def _save_receipt():
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO payment_receipts (order_id, user_id, file_id, note)
                    VALUES ($1, $2, $3, $4)
                ''', order_id, user_id, file_id, note)
                return True

        try:
            return await self.execute_with_retry(_save_receipt)
        except Exception as e:
            logger.error(f"❌ Failed to save payment receipt for order {order_id}: {e}")
            return False

    async def reject_payment(self, order_id: int, rejected_by: int = None) -> bool:
        async def _fn():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    UPDATE delivery_orders
                    SET payment_status = 'rejected',
                        payment_rejected_by = $2,
                        payment_rejected_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1 AND (payment_status IS DISTINCT FROM 'rejected')
                    RETURNING id
                """, order_id, rejected_by)
                return bool(row)
        return await self.execute_with_retry(_fn)

    async def get_payment_receipts_for_order(self, order_id: int):
        async def _get():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM payment_receipts WHERE order_id = $1 ORDER BY created_at DESC
                ''', order_id)
                return [dict(r) for r in rows]
        try:
            return await self.execute_with_retry(_get)
        except Exception as e:
            logger.error(f"❌ Failed to get payment receipts for order {order_id}: {e}")
            return []
