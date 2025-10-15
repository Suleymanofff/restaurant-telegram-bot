from aiogram.fsm.state import State, StatesGroup

class BroadcastStates(StatesGroup):
    """Состояния для создания рассылки"""
    choosing_segment = State()
    choosing_type = State()
    entering_text = State()
    entering_image = State()
    confirming = State()