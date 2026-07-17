"""Аналитика соцсетей: сбор и агрегация событий из каналов и групп Telegram."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.db.models import ChatEvent, TrackedChat


async def track_chat(
    session: AsyncSession,
    chat_id: int,
    title: str | None,
    chat_type: str,
    added_by: int | None,
) -> None:
    existing = await session.scalar(select(TrackedChat).where(TrackedChat.chat_id == chat_id))
    if existing:
        existing.title = title
        existing.chat_type = chat_type
    else:
        session.add(
            TrackedChat(chat_id=chat_id, title=title, chat_type=chat_type, added_by_tg_id=added_by)
        )
    await session.commit()


async def record_event(
    session: AsyncSession, chat_id: int, event_type: str, actor_tg_id: int | None = None
) -> None:
    session.add(ChatEvent(chat_id=chat_id, event_type=event_type, actor_tg_id=actor_tg_id))
    await session.commit()


@dataclass
class ChatStats:
    title: str
    days: int
    messages: int
    posts: int
    joins: int
    leaves: int
    active_users: int
    net_growth: int


async def chat_stats(session: AsyncSession, chat_id: int, days: int = 7) -> ChatStats | None:
    chat = await session.scalar(select(TrackedChat).where(TrackedChat.chat_id == chat_id))
    if chat is None:
        return None
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async def count(event_type: str) -> int:
        return (
            await session.scalar(
                select(func.count())
                .select_from(ChatEvent)
                .where(
                    ChatEvent.chat_id == chat_id,
                    ChatEvent.event_type == event_type,
                    ChatEvent.created_at >= since,
                )
            )
            or 0
        )

    messages = await count("message")
    posts = await count("post")
    joins = await count("join")
    leaves = await count("leave")
    active_users = (
        await session.scalar(
            select(func.count(func.distinct(ChatEvent.actor_tg_id))).where(
                ChatEvent.chat_id == chat_id,
                ChatEvent.event_type == "message",
                ChatEvent.created_at >= since,
            )
        )
        or 0
    )
    return ChatStats(
        title=chat.title or str(chat_id),
        days=days,
        messages=messages,
        posts=posts,
        joins=joins,
        leaves=leaves,
        active_users=active_users,
        net_growth=joins - leaves,
    )


def format_chat_stats(stats: ChatStats) -> str:
    return (
        f"📈 Статистика «{stats.title}» за {stats.days} дн.\n\n"
        f"💬 Сообщений: {stats.messages}\n"
        f"📝 Постов: {stats.posts}\n"
        f"👥 Активных участников: {stats.active_users}\n"
        f"➕ Вступило: {stats.joins}\n"
        f"➖ Вышло: {stats.leaves}\n"
        f"📊 Чистый прирост: {stats.net_growth:+d}"
    )
