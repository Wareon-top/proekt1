from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from wareon.config import settings

_SECTIONS = [
    ("📊 Бизнес-аналитика", "menu:business"),
    ("📣 Аналитика соцсетей", "menu:social"),
    ("🛍 Маркетплейсы", "menu:marketplace"),
    ("📑 Умные таблицы", "menu:tables"),
    ("📋 Отчёты", "menu:reports"),
]


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню. Если задан webapp_url — сверху кнопка открытия дашборда."""
    rows: list[list[InlineKeyboardButton]] = []
    if settings.webapp_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✨ Открыть дашборд",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        )
    rows += [[InlineKeyboardButton(text=text, callback_data=data)] for text, data in _SECTIONS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


BACK_TO_MENU = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]]
)
