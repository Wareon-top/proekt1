from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MAIN_MENU = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Бизнес-аналитика", callback_data="menu:business")],
        [InlineKeyboardButton(text="📣 Аналитика соцсетей", callback_data="menu:social")],
        [InlineKeyboardButton(text="🛍 Маркетплейсы", callback_data="menu:marketplace")],
        [InlineKeyboardButton(text="📑 Умные таблицы", callback_data="menu:tables")],
        [InlineKeyboardButton(text="📋 Отчёты", callback_data="menu:reports")],
    ]
)

BACK_TO_MENU = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")]]
)
