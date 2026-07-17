from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select

from wareon.db.base import session_factory
from wareon.db.models import TableUpload
from wareon.services import qa, tables

router = Router(name="qa")


@router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def on_question(message: Message) -> None:
    """Свободный текст в личке — вопрос к последней загруженной таблице."""
    if message.from_user is None or not message.text:
        return
    async with session_factory() as session:
        upload = await session.scalar(
            select(TableUpload)
            .where(
                TableUpload.user_tg_id == message.from_user.id,
                TableUpload.content.is_not(None),
            )
            .order_by(TableUpload.created_at.desc())
            .limit(1)
        )
    if upload is None or upload.content is None:
        await message.answer(
            "Чтобы я отвечал на вопросы по данным, сначала пришлите таблицу "
            "(.xlsx или .csv). А для расчётов и меню — /start"
        )
        return
    try:
        df = tables.load_table(upload.content, upload.file_name)
    except Exception:
        await message.answer("Не смог перечитать последнюю таблицу — пришлите файл ещё раз.")
        return
    await message.answer(qa.answer(df, message.text, upload.file_name))
