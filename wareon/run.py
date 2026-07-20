"""Единый запуск: Telegram-бот + API в одном процессе с общей базой.

Удобно для хостинга с одним портом (Render / Railway / VPS): и бот, и дашборд/CRM
берут данные из одной БД, поэтому всё оживает одним деплоем. Порт — из PORT.

Локально бот отдельно можно по-прежнему запускать через `python -m wareon.main`.
"""

import asyncio
import logging
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo

from wareon.api.app import app as api_app
from wareon.config import settings
from wareon.db.base import init_db
from wareon.handlers import setup_routers
from wareon.main import BOT_COMMANDS
from wareon.services.scheduler import scheduler_loop

logger = logging.getLogger(__name__)

ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "channel_post",
    "my_chat_member",
    "chat_member",
]


async def run_api() -> None:
    port = int(os.environ.get("PORT", "8080"))
    config = uvicorn.Config(api_app, host="0.0.0.0", port=port, log_level="info")
    await uvicorn.Server(config).serve()


async def run_bot() -> None:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    setup_routers(dp)
    asyncio.create_task(scheduler_loop(bot))
    await bot.set_my_commands(BOT_COMMANDS)
    if settings.webapp_enabled:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Дашборд", web_app=WebAppInfo(url=settings.webapp_launch_url)
            )
        )
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    tasks = [asyncio.create_task(run_api())]
    if settings.bot_token:
        tasks.append(asyncio.create_task(run_bot()))
    else:
        logger.warning("BOT_TOKEN не задан — запускаю только API (без бота).")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
