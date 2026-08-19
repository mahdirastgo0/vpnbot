WELCOME = (
    "👋 سلام {name} عزیز، به ربات فروش کانفیگ VPN خوش اومدی!\n\n"
    "از منوی زیر می‌تونی یه سرویس بخری، کانفیگ‌های فعالت رو ببینی یا با پشتیبانی در ارتباط باشی."
)

CHOOSE_PANEL = "🌍 یکی از لوکیشن‌های زیر رو انتخاب کن:"
CHOOSE_PLAN = "📦 یکی از پلن‌های زیر رو انتخاب کن:"
CHOOSE_PAYMENT = "💳 روش پرداخت رو انتخاب کن:"

NO_PLANS = "در حال حاضر پلن فعالی برای این لوکیشن ثبت نشده. بعداً دوباره امتحان کن."

ORDER_SUMMARY = (
    "🧾 خلاصه سفارش:\n"
    "▫️ لوکیشن: {panel_name}\n"
    "▫️ نوع اتصال: {plan_type}\n"
    "▫️ پلن: {plan_name}\n"
    "▫️ مدت: {duration} روز\n"
    "▫️ حجم: {traffic} گیگابایت\n"
    "▫️ مبلغ: {amount:,} {currency}\n"
)

ZARINPAL_LINK = "برای پرداخت روی دکمه زیر بزن. بعد از پرداخت موفق، کانفیگ به‌صورت خودکار برات ارسال میشه ✅"

CARD_INFO = (
    "💳 لطفاً مبلغ {amount:,} {currency} رو به شماره کارت زیر واریز کن:\n\n"
    "`{card_number}`\n"
    "به نام: {holder}\n"
    "بانک: {bank}\n\n"
    "بعد از واریز، عکس رسید رو همینجا برام بفرست."
)

CARD_RECEIPT_RECEIVED = (
    "✅ رسیدت دریافت شد و برای بررسی به ادمین ارسال شد.\n"
    "به محض تایید، کانفیگت برات ارسال میشه. لطفاً کمی صبر کن 🙏"
)

CRYPTO_CHOOSE_COIN = "🪙 ارز مورد نظر برای پرداخت رو انتخاب کن:"
CRYPTO_INFO = (
    "🪙 لطفاً معادل {amount:,} {currency} رو به آدرس زیر ({coin}) واریز کن:\n\n"
    "`{address}`\n\n"
    "بعد از واریز، هش تراکنش (TxID) رو همینجا برام بفرست."
)
CRYPTO_TX_RECEIVED = (
    "✅ هش تراکنش دریافت شد و برای بررسی به ادمین ارسال شد.\n"
    "به محض تایید، کانفیگت برات ارسال میشه. لطفاً کمی صبر کن 🙏"
)

ORDER_APPROVED_USER = "🎉 پرداختت تایید شد! کانفیگ VPN تو آماده‌ست:"
ORDER_REJECTED_USER = "❌ متاسفانه سفارشت (#{order_id}) توسط ادمین رد شد. برای پیگیری با پشتیبانی در تماس باش: {support}"

ADMIN_NEW_CARD_ORDER = (
    "🆕 سفارش کارت‌به‌کارت جدید #{order_id}\n"
    "کاربر: {user_mention} (ID: {telegram_id})\n"
    "پلن: {plan_name} — {amount:,} {currency}\n"
)
ADMIN_NEW_CRYPTO_ORDER = (
    "🆕 سفارش رمزارزی جدید #{order_id}\n"
    "کاربر: {user_mention} (ID: {telegram_id})\n"
    "پلن: {plan_name} — {amount:,} {currency}\n"
    "ارز: {coin}\n"
    "TxID: `{tx_id}`\n"
)

NOT_ADMIN = "⛔️ این دستور فقط برای ادمین‌هاست."
NO_PENDING_ORDERS = "در حال حاضر سفارش در انتظاری وجود نداره."

MY_CONFIGS_EMPTY = "هنوز هیچ کانفیگ فعالی نداری. از منوی «خرید سرویس» شروع کن 🛒"
MY_CONFIGS_HEADER = "📂 کانفیگ‌های تو ({count} مورد):\n"
MY_CONFIGS_ITEM = (
    "{status_emoji} #{id} | {panel_name} | {type_label}\n"
    "پلن: {plan_name}\n"
    "حجم: {usage}\n"
    "انقضا: {expire_status}\n"
)
MY_CONFIGS_FOOTER = "\nبرای دریافت لینک یا QR هر کانفیگ، روی دکمه‌ی مربوطه بزن 👇"
CONFIG_NOT_FOUND = "این کانفیگ پیدا نشد یا مال تو نیست."
CONFIG_QR_CAPTION = "{panel_name} | {plan_name}\n\n`{link}`"

SUPPORT_TEXT = "برای ارتباط با پشتیبانی به آیدی زیر پیام بده:\n{support}"

CONFIG_NAME_REQUEST = (
    "📝 اسم کانفیگت رو انتخاب کن.\n\n"
    "اسم دلخواهت رو همینجا بفرست، یا روی دکمه زیر بزن تا ربات "
    "یک اسم تصادفی برات انتخاب کنه."
)

CONFIG_NAME_RANDOM = (
    "🎲 اسم کانفیگ انتخاب شد:\n"
    "«{name}»"
)

CONFIG_NAME_SAVED = (
    "✅ اسم کانفیگ «{name}» ثبت شد.\n\n"
    "حالا روش پرداخت رو انتخاب کن:"
)