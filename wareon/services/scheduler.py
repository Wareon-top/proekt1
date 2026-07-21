"""Планировщик регулярных отчётов: ежедневных и еженедельных (время по МСК)."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy import select

from wareon.db.base import session_factory
from wareon.db.models import OutgoingPost, Reminder, ReportSubscription
from wareon.services import ai, reports

MSK = timezone(timedelta(hours=3))
CHECK_INTERVAL_SEC = 30

logger = logging.getLogger(__name__)


def next_run(kind: str, hour: int, minute: int, now_utc: datetime) -> datetime:
    """Ближайший запуск: daily — каждый день, weekly — по понедельникам (время МСК)."""
    now_msk = now_utc.astimezone(MSK)
    candidate = now_msk.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if kind == "weekly":
        candidate += timedelta(days=(0 - candidate.weekday()) % 7)
        if candidate <= now_msk:
            candidate += timedelta(days=7)
    else:
        if candidate <= now_msk:
            candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


async def process_due_subscriptions(bot: Bot) -> int:
    """Отправляет отчёты по подпискам, чей срок наступил. Возвращает число отправок."""
    now = datetime.now(timezone.utc)
    sent = 0
    async with session_factory() as session:
        due = (
            await session.scalars(
                select(ReportSubscription).where(
                    ReportSubscription.next_run_at <= now.replace(tzinfo=None)
                )
            )
        ).all()
        for sub in due:
            try:
                if sub.kind == "ai":
                    brief = await ai.daily_brief(session, sub.user_tg_id)
                    await bot.send_message(sub.user_tg_id, "🧠 Утренняя ИИ-сводка\n\n" + brief)
                else:
                    days = 7 if sub.kind == "weekly" else 1
                    summary = await reports.sales_summary(session, sub.user_tg_id, days)
                    title = (
                        "🗓 Еженедельный отчёт" if sub.kind == "weekly" else "🗓 Ежедневный отчёт"
                    )
                    text = f"{title}\n\n{reports.format_summary(summary)}"
                    chart = reports.revenue_chart_png(summary)
                    if chart:
                        await bot.send_photo(
                            sub.user_tg_id,
                            BufferedInputFile(chart, filename="revenue.png"),
                            caption=text,
                        )
                    else:
                        await bot.send_message(sub.user_tg_id, text)
                sent += 1
            except Exception:
                logger.exception("Не удалось отправить сводку пользователю %s", sub.user_tg_id)
            sub.next_run_at = next_run(sub.kind, sub.hour, sub.minute, now).replace(tzinfo=None)
        await session.commit()
    return sent


async def process_due_reminders(bot: Bot) -> int:
    """Отправляет разовые напоминания, чей срок наступил. Возвращает число отправок."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sent = 0
    async with session_factory() as session:
        due = (
            await session.scalars(
                select(Reminder).where(
                    Reminder.done == False,  # noqa: E712 — SQL
                    Reminder.next_run_at <= now,
                )
            )
        ).all()
        for rem in due:
            try:
                await bot.send_message(rem.user_tg_id, "⏰ Напоминание\n\n" + rem.text)
                sent += 1
            except Exception:
                logger.exception("Не удалось отправить напоминание %s", rem.id)
            rem.done = True
        await session.commit()
    return sent


async def process_ready_posts(bot: Bot) -> int:
    """Публикует одобренные посты (status=ready) в каналы. Возвращает число публикаций."""
    sent = 0
    async with session_factory() as session:
        ready = (
            await session.scalars(select(OutgoingPost).where(OutgoingPost.status == "ready"))
        ).all()
        for post in ready:
            try:
                await bot.send_message(post.chat_id, post.text)
                post.status = "sent"
                sent += 1
                try:
                    await bot.send_message(
                        post.user_tg_id, f"✅ Опубликовал пост в «{post.chat_title}»."
                    )
                except Exception:
                    pass
            except Exception:
                logger.exception("Не удалось опубликовать пост %s", post.id)
                post.status = "failed"
        await session.commit()
    return sent


async def scheduler_loop(bot: Bot) -> None:
    while True:
        try:
            await process_due_subscriptions(bot)
            await process_due_reminders(bot)
            await process_ready_posts(bot)
        except Exception:
            logger.exception("Ошибка планировщика")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
