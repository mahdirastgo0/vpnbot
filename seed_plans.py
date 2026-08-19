"""
پلن‌ها از فایل plans.env خوانده می‌شوند.

برای تغییر پلن‌ها فقط plans.env را تغییر بده
و سپس:

    python seed_plans.py
"""

import asyncio

from app.config import settings
from app.database.crud import upsert_plan
from app.database.engine import async_session, init_db
from app.database.models import PlanType


async def main() -> None:
    await init_db()

    if not settings.PLANS:
        print("❌ هیچ پلنی در plans.env پیدا نشد.")
        return

    async with async_session() as session:

        for data in settings.PLANS:

            plan_type = (
                PlanType.DIRECT
                if data.plan_type == "direct"
                else PlanType.TUNNEL
            )

            plan = await upsert_plan(
                session,
                panel_key=data.panel_key,
                plan_type=plan_type,
                name=data.name,
                duration_days=data.duration_days,
                traffic_gb=data.traffic_gb,
                price=data.price,
                is_active=data.is_active,
            )

            print(
                f"✔ [{plan.panel_key}] "
                f"{plan.plan_type.value:7s} | "
                f"{plan.name} -> "
                f"{plan.price:,} تومان"
            )

    print(
        f"\n✅ {len(settings.PLANS)} پلن "
        f"با موفقیت ثبت/بروزرسانی شد."
    )


if __name__ == "__main__":
    asyncio.run(main())