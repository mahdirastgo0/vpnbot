from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    waiting_card_receipt = State()
    waiting_crypto_txid = State()


class AdminPlanFlow(StatesGroup):
    waiting_panel = State()
    waiting_type = State()
    waiting_name = State()
    waiting_duration = State()
    waiting_traffic = State()
    waiting_price = State()


class AdminBroadcast(StatesGroup):
    waiting_message = State()
