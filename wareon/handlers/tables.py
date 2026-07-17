from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from wareon.db.base import session_factory
from wareon.db.models import TableUpload
from wareon.services import tables

router = Router(name="tables")

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 МБ
SUPPORTED = (".xlsx", ".xlsm", ".xls", ".csv")


@router.message(F.document, F.chat.type == "private")
async def on_document(message: Message, bot: Bot) -> None:
    doc = message.document
    assert doc is not None
    name = (doc.file_name or "file").lower()
    if not name.endswith(SUPPORTED):
        await message.answer("Я умею читать таблицы: пришлите файл .xlsx или .csv")
        return
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer("Файл больше 15 МБ — пришлите таблицу поменьше.")
        return

    await message.answer("⏳ Разбираю таблицу…")
    file = await bot.get_file(doc.file_id)
    assert file.file_path is not None
    buffer = await bot.download_file(file.file_path)
    assert buffer is not None

    file_bytes = buffer.read()
    try:
        df = tables.load_table(file_bytes, doc.file_name or "file.csv")
        summary = tables.summarize_table(df, doc.file_name or "file")
    except Exception:
        await message.answer(
            "Не получилось разобрать файл. Убедитесь, что это корректный .xlsx или .csv."
        )
        return

    if message.from_user:
        async with session_factory() as session:
            session.add(
                TableUpload(
                    user_tg_id=message.from_user.id,
                    file_name=doc.file_name or "file",
                    summary=summary,
                    content=file_bytes,
                )
            )
            await session.commit()
    await message.answer(
        summary
        + "\n\n💬 Теперь можно спрашивать обычным текстом: "
        "«сумма выручки», «топ товаров по выручке», «какой товар принёс больше всего?»"
    )


@router.message(Command("tables"))
async def cmd_tables(message: Message) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        uploads = (
            await session.scalars(
                select(TableUpload)
                .where(TableUpload.user_tg_id == message.from_user.id)
                .order_by(TableUpload.created_at.desc())
                .limit(5)
            )
        ).all()
    if not uploads:
        await message.answer("Вы ещё не загружали таблиц. Пришлите файл .xlsx или .csv.")
        return
    lines = ["📑 Последние таблицы:", ""]
    for u in uploads:
        lines.append(f"• {u.file_name} — {u.created_at.strftime('%d.%m.%Y %H:%M')}")
    await message.answer("\n".join(lines))
