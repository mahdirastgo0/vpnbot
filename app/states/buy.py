from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    waiting_config_name = State()
    waiting_payment_method = State()