from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from wareon.db.base import session_factory
from wareon.services import ai

router = Router(name="ai")


@router.message(Command("brief"))
async def cmd_brief(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer("🧠 Готовлю сводку…")
    async with session_factory() as session:
        text = await ai.daily_brief(session, message.from_user.id)
    await message.answer(text)


@router.message(Command("ask"))
async def cmd_ask(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    question = (command.args or "").strip()
    if not question:
        await message.answer(
            "Задайте вопрос после команды, например:\n"
            "<code>/ask почему упала прибыль?</code>"
        )
        return
    await message.answer("🧠 Думаю…")
    async with session_factory() as session:
        text = await ai.ask(session, message.from_user.id, question)
    await message.answer(text)
