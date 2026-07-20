from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from wareon.config import settings


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню — ИИ-первая сетка кнопок 2×N."""
    rows: list[list[InlineKeyboardButton]] = []
    if settings.webapp_enabled:
        rows.append(
            [InlineKeyboardButton(text="✨ Открыть дашборд", web_app=WebAppInfo(url=settings.webapp_launch_url))]
        )
    rows += [
        [_btn("🧠 Ассистент", "menu:agent"), _btn("🎛 Пульт", "menu:pulse")],
        [_btn("➕ Продажа", "menu:sale"), _btn("📋 Отчёт", "menu:report")],
        [_btn("🧮 Калькуляторы", "menu:calc"), _btn("📑 Таблицы", "menu:tables")],
        [_btn("📣 Соцсети", "menu:social"), _btn("⚙️ Настройки", "menu:settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ В меню", "menu:main")]])


def onboarding_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("▶️ Что ты умеешь", "onb:features")],
            [_btn("🚀 Начать", "menu:main")],
        ]
    )


def features_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🚀 Начать", "menu:main")]])


def agent_card_kb() -> InlineKeyboardMarkup:
    """Раздел «Ассистент» — готовые вопросы одной кнопкой."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📈 Как дела за неделю?", "ask:week")],
            [_btn("💸 Где я теряю деньги?", "ask:loss")],
            [_btn("🎯 Что улучшить первым?", "ask:improve")],
            [_btn("⬅️ В меню", "menu:main")],
        ]
    )


def sale_card_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("▶️ Ввести пошагово", "sale:start")],
            [_btn("⬅️ В меню", "menu:main")],
        ]
    )


def social_card_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📋 Подключённые чаты", "sec:channels")],
            [_btn("⬅️ В меню", "menu:main")],
        ]
    )


def tables_card_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📁 Мои таблицы", "sec:tables")],
            [_btn("⬅️ В меню", "menu:main")],
        ]
    )


# Совместимость со старым импортом.
BACK_TO_MENU = back_menu()


def panel_period_kb() -> InlineKeyboardMarkup:
    """Под пультом — переключатель периода и возврат в меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("7 дней", "pulse:7"), _btn("30 дней", "pulse:30")],
            [_btn("🔄 Обновить", "menu:pulse"), _btn("⬅️ В меню", "menu:main")],
        ]
    )


_AUTONOMY = [
    ("autopilot", "🟢 Автопилот"),
    ("semi", "🟡 Полу-автоном"),
    ("manual", "🔴 Ручной"),
]


def settings_kb(level: str) -> InlineKeyboardMarkup:
    """Настройки: выбор уровня автономии (текущий помечен галочкой)."""
    rows = [
        [_btn(("✅ " if lvl == level else "") + title, f"auto:{lvl}")] for lvl, title in _AUTONOMY
    ]
    rows.append([_btn("⬅️ В меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("7 дней", "report:7"), _btn("30 дней", "report:30")],
            [_btn("⬅️ В меню", "menu:main")],
        ]
    )
