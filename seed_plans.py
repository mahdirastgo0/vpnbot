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

        count = 0

        for key, data in settings.PLANS.items():

            if data.plan_type.upper() == "DIRECT":
                plan_type = PlanType.DIRECT
            elif data.plan_type.upper() == "TUNNEL":
                plan_type = PlanType.TUNNEL
            else:
                print(
                    f"❌ نوع پلن نامعتبر است: "
                    f"{key} -> {data.plan_type}"
                )
                continue

            plan_data = {
                "panel_key": data.panel_key,
                "plan_type": plan_type,
                "name": data.name,
                "description": data.description,
                "duration_days": data.duration_days,
                "traffic_gb": data.traffic_gb,
                "price": data.price,
                "is_active": data.is_active,
            }

            plan = await upsert_plan(
                session,
                **plan_data,
            )

            print(
                f"✔ [{plan.panel_key}] "
                f"{plan.plan_type.value:7s} | "
                f"{plan.name} -> "
                f"{plan.price:,} تومان"
            )

            count += 1

    print(
        f"\n✅ {count} پلن با موفقیت ثبت/بروزرسانی شد."
    )


if __name__ == "__main__":
    asyncio.run(main())