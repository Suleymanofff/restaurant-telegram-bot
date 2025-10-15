from aiogram.fsm.state import State, StatesGroup


class CallStaff(StatesGroup):
    table_number = State()