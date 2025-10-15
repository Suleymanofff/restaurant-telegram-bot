from aiogram.fsm.state import State, StatesGroup

class PaymentStates(StatesGroup):
    choosing_payment_method = State()
    waiting_payment_confirmation = State()