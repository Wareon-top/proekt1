import os

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from wareon.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.sqlalchemy_url)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _tune_sqlite(dbapi_conn, _record) -> None:
    """Разгоняем SQLite: WAL + synchronous=NORMAL — быстрее записи и чтения без
    потери надёжности. Для Postgres не срабатывает."""
    if not settings.sqlalchemy_url.startswith("sqlite"):
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()


async def init_db() -> None:
    from wareon.db import models  # noqa: F401  — регистрирует таблицы в metadata

    # Гарантируем каталог для файла SQLite (например, data/).
    if not settings.database_url and settings.database_path:
        directory = os.path.dirname(settings.database_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
