"""ИИ-оркестратор в боте: /agent — агент во главе, /autonomy — уровень автономии."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import CustomMetric
from wareon.services import agent

router = Router(name="agent")

AUTONOMY_TITLES = {
    "autopilot": "🟢 Автопилот — делаю всё сам",
    "semi": "🟡 Полу-автоном — рутину сам, важное с подтверждением",
    "manual": "🔴 Ручной — только предлагаю",
}

AGENT_HELP = (
    "🧠 <b>ИИ-ассистент (оркестратор)</b>\n\n"
    "Напиши задачу — я посмотрю данные, найду точки роста и узкие места, при "
    "надобности заведу метрику.\n\n"
    "<code>/agent как дела с бизнесом за неделю?</code>\n"
    "<code>/agent заведи метрику доли рекламы в прибыли</code>\n\n"
    "Уровень автономии: <code>/autonomy</code>"
)

AUTONOMY_HELP = (
    "⚙️ <b>Автономия ИИ</b> — насколько я действую сам:\n\n"
    "<code>/autonomy autopilot</code> — 🟢 делаю всё сам\n"
    "<code>/autonomy semi</code> — 🟡 рутину сам, важное с подтверждением\n"
    "<code>/autonomy manual</code> — 🔴 только предлагаю"
)


def _pending_kb(pending: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = []
    for mid, title in pending:
        rows.append(
            [
                InlineKeyboardButton(text=f"✅ Завести «{title}»", callback_data=f"pm:ok:{mid}"),
                InlineKeyboardButton(text="🚫", callback_data=f"pm:no:{mid}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("agent"))
async def cmd_agent(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    task = (command.args or "").strip()
    if not task:
        await message.answer(AGENT_HELP)
        return
    if not settings.ai_enabled:
        await message.answer(agent.ai.DISABLED_MSG)
        return

    thinking = await message.answer("🧠 Думаю…")
    async with session_factory() as session:
        result = await agent.run_agent(session, message.from_user.id, task)

    text = result.text or "…"
    if result.actions:
        text += "\n\n<i>Сделал: " + "; ".join(result.actions) + "</i>"
    try:
        await thinking.edit_text(text)
    except Exception:
        await message.answer(text)
    if result.pending:
        await message.answer(
            "Предлагаю завести метрики — подтвердишь?", reply_markup=_pending_kb(result.pending)
        )


@router.callback_query(F.data.startswith("pm:"))
async def cb_pending_metric(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        return
    try:
        _, action, raw_id = callback.data.split(":")
        metric_id = int(raw_id)
    except ValueError:
        await callback.answer("Не понял кнопку.")
        return

    async with session_factory() as session:
        metric = await session.get(CustomMetric, metric_id)
        if metric is None or metric.user_tg_id != callback.from_user.id:
            await callback.answer("Метрика не найдена.")
            return
        if action == "ok":
            metric.pending = False
            await session.commit()
            note = f"✅ Метрика «{metric.title}» заведена."
        else:
            await session.delete(metric)
            await session.commit()
            note = f"🚫 Метрика «{metric.title}» отклонена."

    await callback.answer()
    if callback.message is not None:
        try:
            await callback.message.edit_text(note)
        except Exception:
            pass


@router.message(Command("autonomy"))
async def cmd_autonomy(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    arg = (command.args or "").strip().lower()
    async with session_factory() as session:
        if not arg:
            level = await agent.get_autonomy(session, message.from_user.id)
            await message.answer(
                f"Текущий уровень: <b>{AUTONOMY_TITLES.get(level, level)}</b>\n\n" + AUTONOMY_HELP
            )
            return
        if arg not in agent.AUTONOMY_LEVELS:
            await message.answer(AUTONOMY_HELP)
            return
        await agent.set_autonomy(session, message.from_user.id, arg)
    await message.answer(f"✅ Уровень автономии: <b>{AUTONOMY_TITLES[arg]}</b>")
