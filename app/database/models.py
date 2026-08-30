import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PaymentMethod(str, enum.Enum):
    ZARINPAL = "zarinpal"
    CARD = "card"
    CRYPTO = "crypto"
    TRIAL = "trial"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PlanType(str, enum.Enum):
    DIRECT = "direct"
    TUNNEL = "tunnel"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    full_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    is_blocked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    trial_used: Mapped[bool] = mapped_column(
    Boolean,
    default=False,
    nullable=False,
    server_default="false",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="user"
    )


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    panel_key: Mapped[str] = mapped_column(
        String(32)
    )

    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        default=PlanType.DIRECT,
    )

    name: Mapped[str] = mapped_column(
        String(128)
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    duration_days: Mapped[int] = mapped_column(
        Integer
    )

    traffic_gb: Mapped[int] = mapped_column(
        Integer
    )

    traffic_mb: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    is_trial: Mapped[bool] = mapped_column(
    Boolean,
    default=False,
    nullable=False,
    server_default="false",
    )

    price: Mapped[int] = mapped_column(
        Integer
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id")
    )

    amount: Mapped[int] = mapped_column(
        Integer
    )

    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod)
    )

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        default=OrderStatus.PENDING,
    )

    # نامی که مشتری برای کانفیگ انتخاب کرده
    config_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # -------------------------
    # زرین پال
    # -------------------------

    zarinpal_authority: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    zarinpal_ref_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # -------------------------
    # کارت به کارت
    # -------------------------

    receipt_file_id: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )

    # -------------------------
    # رمزارز
    # -------------------------

    crypto_coin: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    crypto_tx_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # -------------------------
    # بررسی ادمین
    # -------------------------

    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(
        back_populates="orders"
    )

    plan: Mapped["Plan"] = relationship()

    vpn_config: Mapped["VpnConfig | None"] = relationship(
        back_populates="order",
        uselist=False,
    )


class VpnConfig(Base):
    __tablename__ = "vpn_configs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        unique=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )

    panel_key: Mapped[str] = mapped_column(
        String(32)
    )

    plan_type: Mapped[PlanType] = mapped_column(
        Enum(PlanType),
        default=PlanType.DIRECT,
    )

    plan_name: Mapped[str] = mapped_column(
        String(128),
        default="",
    )

    # نامی که کاربر برای کانفیگ انتخاب کرده
    config_name: Mapped[str] = mapped_column(
        String(128),
        default="کانفیگ من",
        nullable=False,
    )

    inbound_id: Mapped[int] = mapped_column(
        Integer
    )

    client_email: Mapped[str] = mapped_column(
        String(128),
        unique=True,
    )

    client_uuid: Mapped[str] = mapped_column(
        String(64)
    )

    config_link: Mapped[str] = mapped_column(
        Text
    )

    traffic_gb: Mapped[int] = mapped_column(
        Integer
    )

    expire_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    order: Mapped["Order"] = relationship(
        back_populates="vpn_config"
    )

    subscription_link: Mapped[str | None] = mapped_column(
    Text,
    nullable=True,
    )