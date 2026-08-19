from aiogram.filters.callback_data import CallbackData


class ConfigListCallback(CallbackData, prefix="config"):
    config_id: int