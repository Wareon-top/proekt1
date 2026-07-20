from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from wareon.db.base import session_factory
from wareon.db.models import TableUpload
from wareon.keyboards import back_menu
from wareon.services import ingest, tables

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

    ingest_note = ""
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
            # приёмка в «склад» — чтобы данные попали на дашборд
            result = await ingest.ingest_dataframe(session, message.from_user.id, df)
        if result.inserted:
            cols = ", ".join(f"{role}→«{col}»" for role, col in result.mapping.items())
            ingest_note = (
                f"\n\n📥 Загрузил в аналитику: {result.inserted} строк. "
                f"Распознал: {cols}.\nОткрой дашборд — цифры уже там."
            )
        elif result.error:
            ingest_note = f"\n\nℹ️ На дашборд не попало: {result.error}"

    await message.answer(
        summary
        + "\n\n💬 Теперь можно спрашивать обычным текстом: "
        "«сумма выручки», «топ товаров по выручке», «какой товар принёс больше всего?»"
        + ingest_note
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


@router.callback_query(F.data == "sec:tables")
async def cb_tables(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    async with session_factory() as session:
        uploads = (
            await session.scalars(
                select(TableUpload)
                .where(TableUpload.user_tg_id == callback.from_user.id)
                .order_by(TableUpload.created_at.desc())
                .limit(5)
            )
        ).all()
    if not uploads:
        text = (
            "📑 <b>Умные таблицы</b>\n\nТы ещё не загружал таблиц.\n"
            "Пришли файл <b>.xlsx</b> или <b>.csv</b> — разберу и посчитаю."
        )
    else:
        lines = ["📑 <b>Последние таблицы</b>", ""]
        for u in uploads:
            lines.append(f"• {u.file_name} — {u.created_at.strftime('%d.%m.%Y %H:%M')}")
        text = "\n".join(lines)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=back_menu())
        except Exception:
            await callback.message.answer(text, reply_markup=back_menu())
    await callback.answer()
