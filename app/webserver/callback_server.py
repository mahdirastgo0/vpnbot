import logging

from aiohttp import web
from aiogram import Bot

from app.config import settings
from app.database.crud import get_order, mark_order_paid
from app.database.engine import async_session
from app.database.models import OrderStatus
from app.services import zarinpal
from app.services.delivery import provision_and_deliver

logger = logging.getLogger(__name__)

# سفارش‌هایی که callback آن‌ها در حال پردازش است (جلوگیری از پردازش دوباره با رفرش صفحه)
_processing: set[int] = set()


def create_app(bot: Bot) -> web.Application:
    app = web.Application()

    async def zarinpal_callback(request: web.Request) -> web.Response:
        raw_order_id = request.query.get("order_id", "")
        authority = request.query.get("Authority")
        status = request.query.get("Status")

        if not raw_order_id.isdigit() or not authority:
            return web.Response(text="درخواست نامعتبر.", status=400)

        order_id = int(raw_order_id)

        if order_id in _processing:
            return web.Response(text="سفارش در حال پردازش است. لطفاً به ربات برگردید.")

        _processing.add(order_id)
        try:
            return await _handle(order_id, authority, status)
        finally:
            _processing.discard(order_id)

    async def _handle(order_id: int, authority: str, status: str | None) -> web.Response:
        async with async_session() as session:
            order = await get_order(session, order_id)
            if order is None:
                return web.Response(text="سفارش پیدا نشد.", status=404)

            if order.status != OrderStatus.PENDING:
                return web.Response(text="این سفارش قبلاً پردازش شده است.")

            if order.zarinpal_authority and order.zarinpal_authority != authority:
                return web.Response(text="اطلاعات پرداخت با سفارش مطابقت ندارد.", status=400)

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
            except Exception:
                logger.exception("Provision failed for paid zarinpal order %s", order.id)
                try:
                    await bot.send_message(
                        order.user.telegram_id,
                        f"پرداختت با موفقیت انجام شد ولی در ساخت کانفیگ مشکلی پیش اومد. "
                        f"پشتیبانی به‌زودی بهت کمک می‌کنه.\nکد پیگیری: {ref_id}",
                    )
                except Exception:
                    pass
                for admin_id in settings.ADMIN_IDS:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"⚠️ سفارش زرین‌پال #{order.id} پرداخت شد اما ساخت کانفیگ ناموفق بود.\n"
                            f"کد پیگیری: {ref_id}",
                        )
                    except Exception:
                        pass
                return web.Response(
                    text="پرداخت موفق بود ولی ساخت کانفیگ با خطا مواجه شد. پشتیبانی پیگیری می‌کند."
                )

        return web.Response(
            text="✅ پرداخت با موفقیت انجام شد. به تلگرام برگرد، کانفیگت ارسال شده."
        )

    app.router.add_get("/zarinpal/callback", zarinpal_callback)
    return app


async def run_callback_server(bot: Bot) -> web.AppRunner:
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.CALLBACK_SERVER_HOST, settings.CALLBACK_SERVER_PORT)
    await site.start()
    return runner
