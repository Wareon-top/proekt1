"""ИИ-оркестратор в боте: /agent — агент во главе, /autonomy — уровень автономии."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import CustomMetric, OutgoingPost
from wareon.services import agent

router = Router(name="agent")

AUTONOMY_TITLES = {
    "autopilot": "🟢 Автопилот — делаю всё сам",
    "semi": "🟡 Полу-автоном — рутину сам, важное с подтверждением",
    "manual": "🔴 Ручной — только предлагаю",
}

AGENT_HELP = (
    "🧠 <b>Ассистент</b>\n\n"
    "Задай вопрос или дай задачу — посмотрю данные и отвечу по делу.\n\n"
    "<i>Например:</i>\n"
    "• <code>/agent как дела за неделю?</code>\n"
    "• <code>/agent где я теряю деньги?</code>\n"
    "• <code>/agent заведи метрику доли рекламы</code>\n\n"
    "Насколько действую сам — <code>/autonomy</code>."
)

AUTONOMY_HELP = (
    "⚙️ <b>Автономия ассистента</b> — насколько я действую сам:\n\n"
    "🟢 <code>/autonomy autopilot</code> — делаю всё сам\n"
    "🟡 <code>/autonomy semi</code> — рутину сам, важное с подтверждением\n"
    "🔴 <code>/autonomy manual</code> — только предлагаю"
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


def _post_kb(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Опубликовать", callback_data=f"op:ok:{post_id}"),
                InlineKeyboardButton(text="🚫 Отмена", callback_data=f"op:no:{post_id}"),
            ]
        ]
    )


async def _render_pending_posts(message: Message, pending_posts: list[tuple[int, str, str]]) -> None:
    """Показывает подготовленные ИИ посты и кнопки подтверждения публикации."""
    for post_id, chat_title, text in pending_posts:
        preview = (
            f"📝 <b>Пост для «{chat_title}»</b>\n\n"
            f"<blockquote>{text}</blockquote>\n\n"
            "Опубликовать?"
        )
        await message.answer(preview, reply_markup=_post_kb(post_id))


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
    if result.pending_posts:
        await _render_pending_posts(message, result.pending_posts)


QUICK_QUESTIONS = {
    "week": "Как дела с бизнесом за последнюю неделю? Коротко, по делу.",
    "loss": "Где я теряю деньги? Найди узкие места и подскажи, что делать.",
    "improve": "Что улучшить в первую очередь? Дай 3 приоритета.",
}


@router.callback_query(F.data.startswith("ask:"))
async def cb_quick_ask(callback: CallbackQuery) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    question = QUICK_QUESTIONS.get((callback.data or "ask:").split(":", 1)[1])
    if question is None:
        await callback.answer()
        return
    if not settings.ai_enabled:
        await callback.message.edit_text(agent.ai.DISABLED_MSG, reply_markup=_back_kb())
        await callback.answer()
        return
    await callback.answer()
    try:
        await callback.message.edit_text(f"🧠 <i>{question}</i>\n\nДумаю…")
    except Exception:
        pass
    async with session_factory() as session:
        result = await agent.run_agent(session, callback.from_user.id, question)
    text = result.text or "…"
    if result.actions:
        text += "\n\n<i>Сделал: " + "; ".join(result.actions) + "</i>"
    try:
        await callback.message.edit_text(text, reply_markup=_back_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=_back_kb())
    if result.pending:
        await callback.message.answer(
            "Предлагаю завести метрики — подтвердишь?", reply_markup=_pending_kb(result.pending)
        )
    if result.pending_posts:
        await _render_pending_posts(callback.message, result.pending_posts)


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]]
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


@router.callback_query(F.data.startswith("op:"))
async def cb_pending_post(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        return
    try:
        _, action, raw_id = callback.data.split(":")
        post_id = int(raw_id)
    except ValueError:
        await callback.answer("Не понял кнопку.")
        return

    async with session_factory() as session:
        post = await session.get(OutgoingPost, post_id)
        if post is None or post.user_tg_id != callback.from_user.id:
            await callback.answer("Пост не найден.")
            return
        if action == "ok":
            post.status = "ready"
            await session.commit()
            note = f"📢 Публикую пост в «{post.chat_title}»…"
        else:
            await session.delete(post)
            await session.commit()
            note = "🚫 Пост отменён."

    await callback.answer()
    if callback.message is not None:
        try:
            await callback.message.edit_text(note)
        except Exception:
            pass


VOICE_HELP = (
    "🎙 <b>Голос бренда</b> — как я пишу посты и сообщения от твоего имени.\n\n"
    "Опиши свой стиль одной строкой:\n"
    "<code>/voice дружелюбно, на ты, с эмодзи, коротко и по делу</code>\n\n"
    "Дальше буду писать посты в этом тоне."
)


@router.message(Command("voice"))
async def cmd_voice(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    desc = (command.args or "").strip()
    async with session_factory() as session:
        if not desc:
            current = await agent.get_voice(session, message.from_user.id)
            if current:
                await message.answer(
                    f"🎙 Твой голос бренда:\n<blockquote>{current}</blockquote>\n\n"
                    "Изменить — <code>/voice новое описание</code>."
                )
            else:
                await message.answer(VOICE_HELP)
            return
        await agent.set_voice(session, message.from_user.id, desc)
    await message.answer("✅ Запомнил твой голос бренда. Буду писать посты в этом тоне.")


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
