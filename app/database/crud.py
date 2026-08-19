from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Order,
    OrderStatus,
    Plan,
    User,
)


async def get_order(
    session: AsyncSession,
    order_id: int,
) -> Order | None:

    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.plan),
            selectinload(Order.vpn_config),
        )
        .where(Order.id == order_id)
    )

    return result.scalar_one_or_none()


async def get_plan(
    session: AsyncSession,
    plan_id: int,
) -> Plan | None:

    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan_id)
    )

    return result.scalar_one_or_none()


async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
) -> User | None:

    result = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
    )

    return result.scalar_one_or_none()


async def list_pending_orders(
    session: AsyncSession,
) -> list[Order]:

    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.plan),
        )
        .where(Order.status == OrderStatus.PENDING)
        .order_by(Order.id.asc())
    )

    return list(result.scalars().all())


async def mark_order_paid(
    session: AsyncSession,
    order: Order,
    admin_id: int,
) -> None:

    order.status = OrderStatus.PAID
    order.reviewed_by_admin_id = admin_id

    await session.commit()


async def mark_order_rejected(
    session: AsyncSession,
    order: Order,
    admin_id: int,
) -> None:

    order.status = OrderStatus.REJECTED
    order.reviewed_by_admin_id = admin_id

    await session.commit()