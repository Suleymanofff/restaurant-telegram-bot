from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str
    STAFF_IDS: str

    @property
    def admin_ids_list(self) -> List[int]:
        """Преобразует строку ADMIN_IDS в список чисел"""
        if hasattr(self, 'ADMIN_IDS') and self.ADMIN_IDS:
            return [int(admin_id.strip()) for admin_id in self.ADMIN_IDS.split(",")]
        return []

    @property
    def staff_ids_list(self) -> List[int]:
        """Преобразует строку STAFF_IDS в список чисел"""
        if hasattr(self, 'STAFF_IDS') and self.STAFF_IDS:
            return [int(staff_id.strip()) for staff_id in self.STAFF_IDS.split(",")]
        return []

    @property
    def all_staff_ids(self) -> List[int]:
        """Все ID персонала (админы + стафф)"""
        return list(set(self.admin_ids_list + self.staff_ids_list))

    async def is_admin(self, user_id: int, db_manager = None) -> bool:
        """Проверка прав администратора через базу данных"""
        if db_manager:
            return await db_manager.is_admin(user_id)
        # Fallback: проверка через статический список
        admin_ids = [int(admin_id.strip()) for admin_id in self.ADMIN_IDS.split(",")]
        return user_id in admin_ids

    async def is_staff(self, user_id: int, db_manager = None) -> bool:
        """Проверка прав персонала через базу данных"""
        if db_manager:
            return await db_manager.is_staff(user_id)
        # Fallback: проверка через статический список
        staff_ids = [int(staff_id.strip()) for staff_id in self.STAFF_IDS.split(",")]
        return user_id in staff_ids

    def can_receive_staff_notifications(self, user_id: int) -> bool:
        """Проверяет, может ли пользователь получать уведомления (админы + стафф)"""
        return user_id in self.all_staff_ids
    
    # Restaurant location
    RESTAURANT_ADDRESS: str = "Москва, ул. Тверская, 25"
    RESTAURANT_LATITUDE: float = 55.7603
    RESTAURANT_LONGITUDE: float = 37.6185

    # Настройки логирования
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "colored"
    ENABLE_FILE_LOGGING: bool = True
    DATABASE_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()