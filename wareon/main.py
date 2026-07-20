import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

BOT_COMMANDS = [
    BotCommand(command="start", description="🏠 Меню"),
    BotCommand(command="agent", description="🧠 Спросить ассистента"),
    BotCommand(command="pulse", description="🎛 Пульт метрик"),
    BotCommand(command="report", description="📋 Отчёт по продажам"),
    BotCommand(command="sale", description="➕ Записать продажу"),
    BotCommand(command="crm", description="🗂 Таблица клиентов"),
    BotCommand(command="autonomy", description="⚙️ Автономия ИИ"),
    BotCommand(command="subscribe", description="🗓 Регулярные отчёты"),
    BotCommand(command="alert", description="⚠️ Алерт по марже"),
    BotCommand(command="help", description="ℹ️ Что я умею"),
]

from wareon.config import settings
from wareon.db.base import init_db
from wareon.handlers import setup_routers
from wareon.services.scheduler import scheduler_loop


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not settings.bot_token:
        raise SystemExit(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather."
        )

    await init_db()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    setup_routers(dp)

    scheduler_task = asyncio.create_task(scheduler_loop(bot))

    await bot.set_my_commands(BOT_COMMANDS)

    # Кнопка-меню Telegram (рядом с полем ввода) открывает мини-приложение
    if settings.webapp_enabled:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Дашборд", web_app=WebAppInfo(url=settings.webapp_launch_url)
            )
        )

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "callback_query",
                "channel_post",
                "my_chat_member",
                "chat_member",
            ],
        )
    finally:
        scheduler_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
