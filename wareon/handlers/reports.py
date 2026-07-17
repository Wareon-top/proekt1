from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from wareon.db.base import session_factory
from wareon.services import reports

router = Router(name="reports")


@router.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    try:
        days = max(1, min(int((command.args or "").strip()), 365))
    except ValueError:
        days = 7

    async with session_factory() as session:
        summary = await reports.sales_summary(session, message.from_user.id, days)

    text = reports.format_summary(summary)
    chart = reports.revenue_chart_png(summary)
    if chart:
        await message.answer_photo(
            BufferedInputFile(chart, filename="revenue.png"), caption=text
        )
    else:
        await message.answer(text)
