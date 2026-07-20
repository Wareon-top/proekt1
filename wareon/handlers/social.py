from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.chat_member_updated import (
    IS_MEMBER,
    IS_NOT_MEMBER,
    ChatMemberUpdatedFilter,
)
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message
from sqlalchemy import select

from wareon.db.base import session_factory
from wareon.db.models import TrackedChat
from wareon.keyboards import back_menu
from wareon.services import social

router = Router(name="social")

GROUP_TYPES = {"group", "supergroup"}


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def bot_added(event: ChatMemberUpdated) -> None:
    """Бот добавили в канал или группу — начинаем отслеживать."""
    if event.chat.type not in GROUP_TYPES and event.chat.type != "channel":
        return
    async with session_factory() as session:
        await social.track_chat(
            session,
            chat_id=event.chat.id,
            title=event.chat.title,
            chat_type=event.chat.type,
            added_by=event.from_user.id if event.from_user else None,
        )
    if event.chat.type in GROUP_TYPES:
        try:
            await event.answer(
                "✅ Wareon Analytics подключён! Собираю статистику: сообщения, "
                "вступления, выходы. Команда /stats покажет сводку."
            )
        except Exception:
            pass  # нет прав писать — просто молча собираем статистику


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def member_joined(event: ChatMemberUpdated) -> None:
    async with session_factory() as session:
        await social.record_event(
            session, event.chat.id, "join", event.new_chat_member.user.id
        )


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER >> IS_NOT_MEMBER))
async def member_left(event: ChatMemberUpdated) -> None:
    async with session_factory() as session:
        await social.record_event(
            session, event.chat.id, "leave", event.new_chat_member.user.id
        )


@router.channel_post()
async def on_channel_post(message: Message) -> None:
    async with session_factory() as session:
        await social.record_event(session, message.chat.id, "post")


@router.message(Command("stats"), F.chat.type.in_(GROUP_TYPES))
async def cmd_stats_group(message: Message, command: CommandObject) -> None:
    days = _parse_days(command, default=7)
    async with session_factory() as session:
        stats = await social.chat_stats(session, message.chat.id, days)
    if stats is None:
        await message.answer(
            "Я ещё не отслеживаю этот чат. Переподключите меня (удалите и добавьте снова)."
        )
        return
    await message.answer(social.format_chat_stats(stats))


@router.message(Command("channels"), F.chat.type == "private")
async def cmd_channels(message: Message) -> None:
    async with session_factory() as session:
        chats = (await session.scalars(select(TrackedChat))).all()
        if not chats:
            await message.answer(
                "Пока нет подключённых каналов или групп.\n"
                "Добавьте меня в чат администратором — и я начну собирать статистику."
            )
            return
        blocks = []
        for chat in chats:
            stats = await social.chat_stats(session, chat.chat_id, days=7)
            if stats:
                blocks.append(social.format_chat_stats(stats))
    await message.answer("\n\n➖➖➖\n\n".join(blocks))


@router.callback_query(F.data == "sec:channels")
async def cb_channels(callback: CallbackQuery) -> None:
    async with session_factory() as session:
        chats = (await session.scalars(select(TrackedChat))).all()
        blocks = []
        for chat in chats:
            stats = await social.chat_stats(session, chat.chat_id, days=7)
            if stats:
                blocks.append(social.format_chat_stats(stats))
    if blocks:
        text = "📣 <b>Подключённые чаты</b>\n\n" + "\n\n➖➖➖\n\n".join(blocks)
    else:
        text = (
            "📣 <b>Соцсети</b>\n\nПока нет подключённых чатов.\n"
            "Добавь меня в канал или группу администратором — начну считать статистику."
        )
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=back_menu())
        except Exception:
            await callback.message.answer(text, reply_markup=back_menu())
    await callback.answer()


@router.message(F.chat.type.in_(GROUP_TYPES), ~F.text.startswith("/"))
async def on_group_message(message: Message) -> None:
    """Каждое сообщение в отслеживаемой группе — событие активности."""
    async with session_factory() as session:
        await social.record_event(
            session,
            message.chat.id,
            "message",
            message.from_user.id if message.from_user else None,
        )


def _parse_days(command: CommandObject, default: int) -> int:
    try:
        days = int((command.args or "").strip())
        return max(1, min(days, 365))
    except ValueError:
        return default
