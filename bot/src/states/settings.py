from aiogram.fsm.state import State, StatesGroup

class SettingsStates(StatesGroup):
    # Управление персоналом
    waiting_for_admin_id = State()
    waiting_for_staff_id = State()
    waiting_for_remove_admin_id = State()
    waiting_for_remove_staff_id = State()
    
    # Управление меню
    waiting_for_menu_category = State()
    waiting_for_dish_name = State()
    waiting_for_dish_description = State()
    waiting_for_dish_price = State()
    waiting_for_remove_dish_id = State()
    
    # Блокировка пользователей
    waiting_for_block_user_id = State()
    waiting_for_unblock_user_id = State()