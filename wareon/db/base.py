from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from wareon.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(f"sqlite+aiosqlite:///{settings.database_path}")
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from wareon.db import models  # noqa: F401  — регистрирует таблицы в metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
