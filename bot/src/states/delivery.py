from aiogram.fsm.state import State, StatesGroup

class DeliveryStates(StatesGroup):
    choosing_category = State()
    viewing_menu = State()
    viewing_cart = State()
    entering_name = State()
    entering_phone = State()
    entering_address = State()
    entering_referral = State()
    using_bonus = State()
    confirming_order = State()