from aiogram import Router

from . import broadcast, menu, payments, plans

admin_router = Router(name="admin")
admin_router.include_router(menu.router)
admin_router.include_router(plans.router)
admin_router.include_router(payments.router)
admin_router.include_router(broadcast.router)
