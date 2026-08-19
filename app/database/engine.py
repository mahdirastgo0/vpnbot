from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """جداول را در صورت عدم وجود می‌سازد (برای شروع سریع، بدون alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
