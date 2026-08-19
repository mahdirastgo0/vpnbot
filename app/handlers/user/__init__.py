from aiogram import Router

from . import buy, my_configs, payment, start

user_router = Router(name="user")
user_router.include_router(start.router)
user_router.include_router(buy.router)
user_router.include_router(payment.router)
user_router.include_router(my_configs.router)
