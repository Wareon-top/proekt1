import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import delete, select

from wareon.db.base import session_factory
from wareon.db.models import AlertSetting, ReportSubscription
from wareon.services.scheduler import MSK, next_run

router = Router(name="schedule")

SUBSCRIBE_HELP = (
    "🗓 <b>Регулярные отчёты</b> (время московское)\n\n"
    "<code>/subscribe daily 09:00</code> — ежедневный отчёт\n"
    "<code>/subscribe weekly 10:00</code> — еженедельный, по понедельникам\n"
    "<code>/unsubscribe</code> — отключить все\n\n"
    "⚠️ <b>Алерты</b>\n"
    "<code>/alert 20</code> — предупреждать, если маржа за сутки ниже 20%\n"
    "<code>/alert off</code> — выключить алерт"
)


def _parse_time(arg: str | None, default_hour: int) -> tuple[int, int] | None:
    if not arg:
        return default_hour, 0
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", arg.strip())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


@router.message(Command("subscribe"), F.chat.type == "private")
async def cmd_subscribe(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    args = (command.args or "").split()
    if not args:
        async with session_factory() as session:
            subs = (
                await session.scalars(
                    select(ReportSubscription).where(
                        ReportSubscription.user_tg_id == message.from_user.id
                    )
                )
            ).all()
        if subs:
            lines = ["Текущие подписки:"]
            for s in subs:
                kind = "ежедневно" if s.kind == "daily" else "еженедельно (пн)"
                lines.append(f"• {kind} в {s.hour:02d}:{s.minute:02d} МСК")
            lines.append("")
            lines.append(SUBSCRIBE_HELP)
            await message.answer("\n".join(lines))
        else:
            await message.answer(SUBSCRIBE_HELP)
        return

    kind = args[0].lower()
    if kind not in ("daily", "weekly"):
        await message.answer(SUBSCRIBE_HELP)
        return
    parsed = _parse_time(args[1] if len(args) > 1 else None, default_hour=9)
    if parsed is None:
        await message.answer("Время укажите как ЧЧ:ММ, например <code>09:30</code>.")
        return
    hour, minute = parsed

    now = datetime.now(timezone.utc)
    run_at = next_run(kind, hour, minute, now).replace(tzinfo=None)
    async with session_factory() as session:
        existing = await session.scalar(
            select(ReportSubscription).where(
                ReportSubscription.user_tg_id == message.from_user.id,
                ReportSubscription.kind == kind,
            )
        )
        if existing:
            existing.hour, existing.minute, existing.next_run_at = hour, minute, run_at
        else:
            session.add(
                ReportSubscription(
                    user_tg_id=message.from_user.id,
                    kind=kind,
                    hour=hour,
                    minute=minute,
                    next_run_at=run_at,
                )
            )
        await session.commit()

    kind_ru = "Ежедневный" if kind == "daily" else "Еженедельный (по понедельникам)"
    first = run_at.replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%d.%m в %H:%M")
    await message.answer(
        f"✅ {kind_ru} отчёт включён — {hour:02d}:{minute:02d} МСК.\n"
        f"Первый придёт {first} (МСК)."
    )


@router.message(Command("unsubscribe"), F.chat.type == "private")
async def cmd_unsubscribe(message: Message) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        await session.execute(
            delete(ReportSubscription).where(
                ReportSubscription.user_tg_id == message.from_user.id
            )
        )
        await session.commit()
    await message.answer("Все подписки на отчёты отключены.")


@router.message(Command("alert"), F.chat.type == "private")
async def cmd_alert(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    arg = (command.args or "").strip().lower()
    async with session_factory() as session:
        if not arg:
            setting = await session.scalar(
                select(AlertSetting).where(AlertSetting.user_tg_id == message.from_user.id)
            )
            if setting:
                await message.answer(
                    f"⚠️ Алерт включён: маржа за сутки ниже "
                    f"{setting.margin_threshold_pct:g}%.\nВыключить: <code>/alert off</code>"
                )
            else:
                await message.answer(
                    "Алерт выключен. Включить: <code>/alert 20</code> — "
                    "предупрежу, когда маржа за сутки упадёт ниже 20%."
                )
            return
        if arg in ("off", "выкл"):
            await session.execute(
                delete(AlertSetting).where(AlertSetting.user_tg_id == message.from_user.id)
            )
            await session.commit()
            await message.answer("Алерт по марже выключен.")
            return
        try:
            threshold = float(arg.replace(",", "."))
            if not 0 < threshold < 100:
                raise ValueError
        except ValueError:
            await message.answer("Укажите порог в процентах: <code>/alert 20</code>")
            return
        setting = await session.scalar(
            select(AlertSetting).where(AlertSetting.user_tg_id == message.from_user.id)
        )
        if setting:
            setting.margin_threshold_pct = threshold
        else:
            session.add(
                AlertSetting(user_tg_id=message.from_user.id, margin_threshold_pct=threshold)
            )
        await session.commit()
    await message.answer(
        f"✅ Алерт включён: предупрежу, если маржа за сутки опустится ниже {threshold:g}%."
    )
