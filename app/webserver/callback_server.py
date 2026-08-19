from aiohttp import web
from aiogram import Bot

from app.config import settings
from app.database.crud import get_order, mark_order_paid
from app.database.engine import async_session
from app.database.models import OrderStatus
from app.services import zarinpal
from app.services.delivery import provision_and_deliver
from app.services.sanaei_client import SanaeiApiError


def create_app(bot: Bot) -> web.Application:
    app = web.Application()

    async def zarinpal_callback(request: web.Request) -> web.Response:
        order_id = request.query.get("order_id")
        authority = request.query.get("Authority")
        status = request.query.get("Status")

        if not order_id or not authority:
            return web.Response(text="درخواست نامعتبر.", status=400)

        async with async_session() as session:
            order = await get_order(session, int(order_id))
            if order is None:
                return web.Response(text="سفارش پیدا نشد.", status=404)

            if order.status != OrderStatus.PENDING:
                return web.Response(text="این سفارش قبلاً پردازش شده است.")

            if status != "OK":
                return web.Response(text="پرداخت توسط شما لغو شد. می‌توانید به ربات برگردید و دوباره تلاش کنید.")

            try:
                ref_id = await zarinpal.verify_payment(order.amount, authority)
            except zarinpal.ZarinpalError as e:
                return web.Response(text=f"پرداخت تایید نشد: {e}", status=400)

            order.zarinpal_ref_id = ref_id
            await mark_order_paid(session, order)

            try:
                await provision_and_deliver(bot, session, order)
            except SanaeiApiError as e:
                await bot.send_message(
                    order.user.telegram_id,
                    f"پرداختت با موفقیت انجام شد ولی در ساخت کانفیگ مشکلی پیش اومد. "
                    f"پشتیبانی به‌زودی بهت کمک می‌کنه.\nکد پیگیری: {ref_id}",
                )
                return web.Response(text=f"پرداخت موفق ولی خطا در ساخت کانفیگ: {e}")

        return web.Response(
            text="✅ پرداخت با موفقیت انجام شد. به تلگرام برگرد، کانفیگت ارسال شده."
        )

    app.router.add_get("/zarinpal/callback", zarinpal_callback)
    return app


async def run_callback_server(bot: Bot) -> None:
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.CALLBACK_SERVER_HOST, settings.CALLBACK_SERVER_PORT)
    await site.start()
