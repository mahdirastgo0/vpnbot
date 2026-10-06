import asyncio

from sqlalchemy import select

from app.database.engine import async_session, init_db
from app.database.models import Plan, PlanType


TRIALS = [
    {
        "panel_key": "nthr",
        "plan_type": PlanType.DIRECT,
        "name": "🎁 تست رایگان لهستان",
        "duration_days": 1,
        "traffic_gb": 1,
        "traffic_mb": 1024,
        "price": 0,
    },
    {
        "panel_key": "ir1",
        "plan_type": PlanType.TUNNEL,
        "name": "🎁 تست رایگان ایران",
        "duration_days": 1,
        "traffic_gb": 1,
        "traffic_mb": 1024,
        "price": 0,
    },
]


async def main() -> None:
    await init_db()

    async with async_session() as session:
        for t in TRIALS:
            result = await session.execute(
                select(Plan).where(Plan.name == t["name"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"⏭ پلن تست «{t['name']}» از قبل هست.")
                continue

            plan = Plan(
                panel_key=t["panel_key"],
                plan_type=t["plan_type"],
                name=t["name"],
                duration_days=t["duration_days"],
                traffic_gb=t["traffic_gb"],
                traffic_mb=t["traffic_mb"],
                price=t["price"],
                is_active=True,
                is_trial=True,
            )
            session.add(plan)
            print(f"✔ پلن تست «{t['name']}» اضافه شد.")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())