import asyncio

from sqlalchemy import select

from app.config import settings
from app.database.engine import async_session, init_db
from app.database.models import Plan, PlanType


async def main() -> None:
    await init_db()

    if not settings.PLANS:
        print("❌ هیچ پلنی در plans.env پیدا نشد.")
        print("   چک کن که خط PLANS=... توی plans.env باشه.")
        return

    async with async_session() as session:

        created = 0
        updated = 0

        for key, data in settings.PLANS.items():

            if data.plan_type.upper() == "DIRECT":
                plan_type = PlanType.DIRECT
            elif data.plan_type.upper() == "TUNNEL":
                plan_type = PlanType.TUNNEL
            else:
                print(f"❌ نوع پلن نامعتبر: {key} -> {data.plan_type}")
                continue

            # چک کن این پلن قبلاً هست؟
            result = await session.execute(
                select(Plan).where(Plan.name == data.name)
            )
            plan = result.scalar_one_or_none()

            if plan is not None:
                plan.panel_key = data.panel_key
                plan.plan_type = plan_type
                plan.duration_days = data.duration_days
                plan.traffic_gb = data.traffic_gb
                plan.price = data.price
                plan.is_active = data.is_active
                updated += 1
                print(f"🔄 [{plan.panel_key}] {plan.name} بروزرسانی شد")
            else:
                plan = Plan(
                    panel_key=data.panel_key,
                    plan_type=plan_type,
                    name=data.name,
                    duration_days=data.duration_days,
                    traffic_gb=data.traffic_gb,
                    price=data.price,
                    is_active=data.is_active,
                    is_trial=False,
                )
                session.add(plan)
                created += 1
                print(f"✔ [{data.panel_key}] {data.name} -> {data.price:,} تومان")

        await session.commit()

    print(f"\n✅ {created} پلن جدید | {updated} پلن بروزرسانی شد.")


if __name__ == "__main__":
    asyncio.run(main())