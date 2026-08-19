from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Order,
    OrderStatus,
    Plan,
    PlanType,
    User,
    PaymentMethod,
)


# ==========================================================
# USER
# ==========================================================

async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: int,
) -> User | None:

    result = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
    )

    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    full_name: str | None = None,
) -> User:

    user = await get_user_by_telegram_id(
        session,
        telegram_id,
    )

    if user is not None:

        user.username = username
        user.full_name = full_name

        await session.commit()
        await session.refresh(user)

        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
    )

    session.add(user)

    await session.commit()
    await session.refresh(user)

    return user


# ==========================================================
# PLANS
# ==========================================================

async def get_plan(
    session: AsyncSession,
    plan_id: int,
) -> Plan | None:

    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan_id)
    )

    return result.scalar_one_or_none()


async def list_active_plans(
    session: AsyncSession,
    panel_key: str | None = None,
) -> list[Plan]:

    query = (
        select(Plan)
        .where(Plan.is_active.is_(True))
        .order_by(
            Plan.plan_type.asc(),
            Plan.price.asc(),
            Plan.id.asc(),
        )
    )

    if panel_key is not None:
        query = query.where(
            Plan.panel_key == panel_key
        )

    result = await session.execute(query)

    return list(result.scalars().all())


async def list_all_plans(
    session: AsyncSession,
) -> list[Plan]:

    result = await session.execute(
        select(Plan)
        .order_by(
            Plan.id.asc()
        )
    )

    return list(result.scalars().all())


async def create_plan(
    session: AsyncSession,
    panel_key: str,
    plan_type: PlanType,
    name: str,
    duration_days: int,
    traffic_gb: int,
    price: int,
    description: str | None = None,
    is_active: bool = True,
) -> Plan:

    plan = Plan(
        panel_key=panel_key,
        plan_type=plan_type,
        name=name,
        duration_days=duration_days,
        traffic_gb=traffic_gb,
        price=price,
        description=description,
        is_active=is_active,
    )

    session.add(plan)

    await session.commit()
    await session.refresh(plan)

    return plan


async def update_plan(
    session: AsyncSession,
    plan: Plan,
    **kwargs,
) -> Plan:

    for key, value in kwargs.items():

        if hasattr(plan, key):
            setattr(plan, key, value)

    await session.commit()
    await session.refresh(plan)

    return plan


async def delete_plan(
    session: AsyncSession,
    plan: Plan,
) -> None:

    await session.delete(plan)
    await session.commit()


# ==========================================================
# ORDERS
# ==========================================================

async def create_order(
    session: AsyncSession,
    user: User,
    plan: Plan,
    payment_method: PaymentMethod,
    config_name: str | None = None,
) -> Order:

    order = Order(
        user_id=user.id,
        plan_id=plan.id,
        amount=plan.price,
        payment_method=payment_method,
        status=OrderStatus.PENDING,
        config_name=config_name,
    )

    session.add(order)

    await session.commit()

    # دوباره با relationshipهای لازم می‌خوانیم
    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.plan),
            selectinload(Order.vpn_config),
        )
        .where(Order.id == order.id)
    )

    return result.scalar_one()


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


async def list_pending_orders(
    session: AsyncSession,
) -> list[Order]:

    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.plan),
            selectinload(Order.vpn_config),
        )
        .where(
            Order.status == OrderStatus.PENDING
        )
        .order_by(
            Order.id.asc()
        )
    )

    return list(result.scalars().all())


async def list_user_orders(
    session: AsyncSession,
    user_id: int,
) -> list[Order]:

    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.plan),
            selectinload(Order.vpn_config),
        )
        .where(
            Order.user_id == user_id
        )
        .order_by(
            Order.id.desc()
        )
    )

    return list(result.scalars().all())


async def list_paid_orders(
    session: AsyncSession,
) -> list[Order]:

    result = await session.execute(
        select(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.plan),
            selectinload(Order.vpn_config),
        )
        .where(
            Order.status == OrderStatus.PAID
        )
        .order_by(
            Order.id.desc()
        )
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


async def mark_order_cancelled(
    session: AsyncSession,
    order: Order,
) -> None:

    order.status = OrderStatus.CANCELLED

    await session.commit()


# ==========================================================
# ZARINPAL
# ==========================================================

async def set_zarinpal_authority(
    session: AsyncSession,
    order: Order,
    authority: str,
) -> None:

    order.zarinpal_authority = authority

    await session.commit()


async def set_zarinpal_ref_id(
    session: AsyncSession,
    order: Order,
    ref_id: str,
) -> None:

    order.zarinpal_ref_id = ref_id

    await session.commit()


# ==========================================================
# CARD TO CARD
# ==========================================================

async def set_receipt_file(
    session: AsyncSession,
    order: Order,
    file_id: str,
) -> None:

    order.receipt_file_id = file_id

    await session.commit()


# ==========================================================
# CRYPTO
# ==========================================================

async def set_crypto_payment(
    session: AsyncSession,
    order: Order,
    coin: str,
    tx_id: str,
) -> None:

    order.crypto_coin = coin
    order.crypto_tx_id = tx_id

    await session.commit()


# ==========================================================
# VPN CONFIGS
# ==========================================================

async def get_user_configs(
    session: AsyncSession,
    user_id: int,
):

    from app.database.models import VpnConfig

    result = await session.execute(
        select(VpnConfig)
        .where(
            VpnConfig.user_id == user_id
        )
        .order_by(
            VpnConfig.id.desc()
        )
    )

    return list(result.scalars().all())


async def get_config(
    session: AsyncSession,
    config_id: int,
):

    from app.database.models import VpnConfig

    result = await session.execute(
        select(VpnConfig)
        .where(
            VpnConfig.id == config_id
        )
    )

    return result.scalar_one_or_none()

async def get_vpn_config(
    session: AsyncSession,
    config_id: int,
):
    return await get_config(
        session,
        config_id,
    )


async def list_user_configs(
    session: AsyncSession,
    user_id: int,
):
    from app.database.models import VpnConfig

    result = await session.execute(
        select(VpnConfig)
        .where(
            VpnConfig.user_id == user_id
        )
        .order_by(
            VpnConfig.id.desc()
        )
    )

    return list(result.scalars().all())

async def get_config_for_user(
    session: AsyncSession,
    config_id: int,
    user_id: int,
):

    from app.database.models import VpnConfig

    result = await session.execute(
        select(VpnConfig)
        .where(
            VpnConfig.id == config_id,
            VpnConfig.user_id == user_id,
        )
    )

    return result.scalar_one_or_none()