"""
پلن‌ها و قیمت‌ها را اینجا به‌صورت کد تعریف کن، سپس اجرا کن:

    python seed_plans.py

- اجرای دوباره‌ی این اسکریپت مشکلی نداره: پلن‌هایی که panel_key + name یکسان دارن
  فقط آپدیت می‌شن (نه تکراری).
- panel_key باید دقیقاً همون کلیدی باشه که توی PANELS در .env تعریف کردی
  (مثلاً اگر PANELS=pol1,de1 باشه، اینجا هم باید از "pol1" یا "de1" استفاده کنی).
- plan_type: PlanType.DIRECT (مستقیم) یا PlanType.TUNNEL (تانل).
- price به تومان و traffic_gb به گیگابایت است؛ traffic_gb=0 یعنی نامحدود.

توجه: پلن‌ها در فایل .env تعریف نمی‌شن (فقط اطلاعات اتصال پنل‌ها اونجاست)،
چون هر پنل می‌تونه چندین پلن با قیمت/حجم متفاوت داشته باشه و مدیریتشون با کد یا
با دستور /addplan داخل ربات خیلی راحت‌تر از فایل .env است.
"""
import asyncio

from app.database.crud import upsert_plan
from app.database.engine import async_session, init_db
from app.database.models import PlanType

# ----------------------------------------------------------------------------
# 👇 این لیست رو با پلن‌های واقعی خودت جایگزین کن
# ----------------------------------------------------------------------------
PLANS = [
    # ---------- پنل pol1 (لهستان) - اتصال مستقیم ----------
    dict(
        panel_key="pol1",
        plan_type=PlanType.DIRECT,
        name="۱ ماهه ۳۰ گیگ - مستقیم",
        duration_days=30,
        traffic_gb=30,
        price=150_000,
    ),
    dict(
        panel_key="pol1",
        plan_type=PlanType.DIRECT,
        name="۱ ماهه ۶۰ گیگ - مستقیم",
        duration_days=30,
        traffic_gb=60,
        price=250_000,
    ),
    dict(
        panel_key="pol1",
        plan_type=PlanType.DIRECT,
        name="۱ ماهه نامحدود - مستقیم",
        duration_days=30,
        traffic_gb=0,
        price=400_000,
    ),
    # ---------- پنل pol1 (لهستان) - از طریق تانل (پایدارتر، حجم بیشتر، گران‌تر) ----------
    dict(
        panel_key="pol1",
        plan_type=PlanType.TUNNEL,
        name="۱ ماهه ۵۰ گیگ - تانل",
        duration_days=30,
        traffic_gb=50,
        price=220_000,
    ),
    dict(
        panel_key="pol1",
        plan_type=PlanType.TUNNEL,
        name="۱ ماهه ۱۰۰ گیگ - تانل",
        duration_days=30,
        traffic_gb=100,
        price=350_000,
    ),
    # ---------- برای هر پنل دیگه‌ای که توی .env داری، به همین شکل اضافه کن ----------
    # dict(
    #     panel_key="de1",
    #     plan_type=PlanType.DIRECT,
    #     name="۱ ماهه ۳۰ گیگ - آلمان مستقیم",
    #     duration_days=30,
    #     traffic_gb=30,
    #     price=180_000,
    # ),
]
# ----------------------------------------------------------------------------


async def main() -> None:
    await init_db()
    async with async_session() as session:
        for data in PLANS:
            plan = await upsert_plan(session, **data)
            print(f"✔ [{plan.panel_key}] {plan.plan_type.value:7s} | {plan.name} -> {plan.price:,} تومان")

    print(f"\n✅ {len(PLANS)} پلن با موفقیت ثبت/بروزرسانی شد. حالا /plans رو توی ربات بزن تا ببینیشون.")


if __name__ == "__main__":
    asyncio.run(main())
