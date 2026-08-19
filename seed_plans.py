import asyncio

from app.config import settings
from app.database.crud import upsert_plan
from app.database.engine import async_session, init_db
from app.database.models import PlanType


async def main() -> None:

    await init_db()

    async with async_session() as session:

        for plan_key, data in settings.PLANS.items():

            plan = await upsert_plan(
                session,

                panel_key=data.panel_key,

                plan_type=PlanType(data.plan_type),

                name=data.name,

                description=data.description,

                duration_days=data.duration_days,

                traffic_gb=data.traffic_gb,

                price=data.price,

                is_active=data.is_active,
            )

            status = "فعال" if plan.is_active else "غیرفعال"

            print(
                f"✔ [{plan.panel_key}] "
                f"{plan.plan_type.value:7s} | "
                f"{plan.name} | "
                f"{plan.traffic_gb}GB | "
                f"{plan.price:,} تومان | "
                f"{status}"
            )

    print(
        f"\n✅ {len(settings.PLANS)} پلن "
        f"از .env با موفقیت sync شد."
    )


if __name__ == "__main__":
    asyncio.run(main())