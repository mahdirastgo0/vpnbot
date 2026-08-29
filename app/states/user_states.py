from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    waiting_config_name = State()
    waiting_card_receipt = State()
    waiting_crypto_txid = State()


class AdminPlanFlow(StatesGroup):
    # افزودن سرویس
    waiting_panel = State()
    waiting_type = State()
    waiting_name = State()
    waiting_duration = State()
    waiting_traffic = State()
    waiting_price = State()

    # ویرایش سرویس
    waiting_edit_name = State()
    waiting_edit_duration = State()
    waiting_edit_traffic = State()
    waiting_edit_price = State()


class AdminBroadcast(StatesGroup):
    waiting_message = State()