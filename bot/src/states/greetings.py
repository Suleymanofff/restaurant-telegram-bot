from aiogram.fsm.state import State, StatesGroup


class Greeting(StatesGroup):
    get_sex = State()
    get_major = State()
    open_main_menu = State()