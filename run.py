import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database.engine import init_db
from app.handlers.admin import admin_router
from app.handlers.user import user_router
from app.middlewares.db_middleware import DbSessionMiddleware
from app.services.panel_manager import close_all
from app.webserver.callback_server import run_callback_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(admin_router)
    dp.include_router(user_router)

    await init_db()
    logger.info("دیتابیس آماده شد.")

    await run_callback_server(bot)
    logger.info(
        "وب‌سرور کال‌بک زرین‌پال روی %s:%s بالا آمد.",
        settings.CALLBACK_SERVER_HOST,
        settings.CALLBACK_SERVER_PORT,
    )

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("ربات در حال اجراست...")
        await dp.start_polling(bot)
    finally:
        await close_all()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
