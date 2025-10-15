from aiogram.fsm.state import State, StatesGroup

class ReservationStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_guests = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    confirmation = State()