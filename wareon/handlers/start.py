from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import User
from wareon.keyboards import (
    back_menu,
    main_menu,
    panel_period_kb,
    report_kb,
    settings_kb,
)
from wareon.services import agent, reports
from wareon.services.metrics import build_panel

router = Router(name="start")

WELCOME = (
    "👋 Я <b>Wareon</b> — ИИ бизнес-ассистент.\n\n"
    "Вижу твои цифры, нахожу <b>точки роста</b> и <b>узкие места</b>, подсказываю "
    "и действую. Таблицы — лишь наглядная подача; во главе — ИИ.\n\n"
    "Жми кнопки ниже — или просто напиши мне вопрос."
)

DASHBOARD_HINT = "\n\n✨ «Открыть дашборд» — вся глубина в одном экране."


def welcome_text() -> str:
    return WELCOME + (DASHBOARD_HINT if settings.webapp_enabled else "")


AGENT_CARD = (
    "🧠 <b>Ассистент</b>\n\n"
    "Задай вопрос или дай задачу — я посмотрю данные, найду точки роста и узкие "
    "места, при надобности заведу метрику.\n\n"
    "<code>/agent как дела с бизнесом за неделю?</code>\n"
    "<code>/agent заведи метрику доли рекламы</code>\n\n"
    "Можно и без команды — просто напиши мне сообщение."
)

SALE_CARD = (
    "➕ <b>Записать продажу</b>\n\n"
    "<code>/sale выручка [себестоимость] [источник]</code>\n"
    "Например: <code>/sale 15000 8000 сайт</code>\n\n"
    "После пары продаж жми 🎛 <b>Пульт</b> — увижу тренды и подскажу."
)

SECTION_HELP = {
    "social": (
        "📣 <b>Аналитика соцсетей</b>\n\n"
        "1. Добавь меня в канал или группу администратором\n"
        "2. Я начну собирать статистику: сообщения, посты, подписки, отписки\n"
        "3. В группе — команда <code>/stats</code>\n"
        "4. Здесь, в личке — <code>/channels</code>, список подключённых чатов\n\n"
        "Подключение других соцсетей — слой развития."
    ),
    "marketplace": (
        "🛍 <b>Аналитика маркетплейсов</b>\n\n"
        "Для дизайнеров карточек и менеджеров:\n"
        "<code>/card 50000 2500 400 120</code> — воронка карточки "
        "(показы, клики, корзины, заказы)\n"
        "<code>/card 50000 2500 400 120 30000 180000</code> — то же + ДРР\n"
        "<code>/unit 1500 20 80 600 50</code> — юнит-экономика "
        "(цена, комиссия %, логистика, себестоимость, реклама на ед.)"
    ),
    "tables": (
        "📑 <b>Умные таблицы</b>\n\n"
        "Пришли файл <b>.xlsx</b> или <b>.csv</b> — разберу структуру, посчитаю "
        "суммы и средние, найду топ-категории и пустые ячейки.\n\n"
        "Потом задавай вопросы обычным текстом:\n"
        "• «сумма выручки»\n• «топ товаров по выручке»\n\n"
        "<code>/tables</code> — история загруженных таблиц"
    ),
}

AUTONOMY_TITLES = {
    "autopilot": "🟢 Автопилот — делаю всё сам",
    "semi": "🟡 Полу-автоном — рутину сам, важное с подтверждением",
    "manual": "🔴 Ручной — только предлагаю",
}


async def _edit(callback: CallbackQuery, text: str, markup) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception:
            await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user:
        async with session_factory() as session:
            exists = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
            if not exists:
                session.add(User(tg_id=message.from_user.id, username=message.from_user.username))
                await session.commit()
    await message.answer(welcome_text(), reply_markup=main_menu())


@router.callback_query(F.data == "menu:main")
async def cb_main(callback: CallbackQuery) -> None:
    await _edit(callback, welcome_text(), main_menu())


@router.callback_query(F.data == "menu:agent")
async def cb_agent_card(callback: CallbackQuery) -> None:
    await _edit(callback, AGENT_CARD, back_menu())


@router.callback_query(F.data == "menu:sale")
async def cb_sale_card(callback: CallbackQuery) -> None:
    await _edit(callback, SALE_CARD, back_menu())


# ── Пульт прямо в меню ────────────────────────────────────────────────────────
async def _render_panel(callback: CallbackQuery, days: int) -> None:
    from wareon.handlers.pulse import format_panel

    if callback.from_user is None:
        return
    async with session_factory() as session:
        panel = await build_panel(session, callback.from_user.id, days=days)
    revenue = next((m for m in panel.metrics if m.key == "revenue"), None)
    if revenue is None or not revenue.value:
        text = (
            f"🎛 <b>Пульт</b>\n\nЗа {days} дн продаж нет.\n"
            "Добавь продажу: <code>/sale 15000 8000</code>"
        )
    else:
        text = format_panel(panel)
    await _edit(callback, text, panel_period_kb())


@router.callback_query(F.data == "menu:pulse")
async def cb_pulse(callback: CallbackQuery) -> None:
    await _render_panel(callback, 7)


@router.callback_query(F.data.startswith("pulse:"))
async def cb_pulse_period(callback: CallbackQuery) -> None:
    try:
        days = int((callback.data or "pulse:7").split(":")[1])
    except ValueError:
        days = 7
    await _render_panel(callback, days)


# ── Отчёт прямо в меню ────────────────────────────────────────────────────────
async def _render_report(callback: CallbackQuery, days: int) -> None:
    if callback.from_user is None:
        return
    async with session_factory() as session:
        summary = await reports.sales_summary(session, callback.from_user.id, days)
    if summary.orders == 0:
        text = (
            f"📋 <b>Отчёт</b>\n\nЗа {days} дн продаж нет.\n"
            "Добавь продажу: <code>/sale 15000 8000</code>"
        )
    else:
        text = f"📋 <b>Отчёт за {days} дн</b>\n\n{reports.format_summary(summary)}"
    text += (
        "\n\nАвто-отчёты: <code>/subscribe daily 09:00</code>, "
        "алерт по марже: <code>/alert 20</code>"
    )
    await _edit(callback, text, report_kb())


@router.callback_query(F.data == "menu:report")
async def cb_report(callback: CallbackQuery) -> None:
    await _render_report(callback, 7)


@router.callback_query(F.data.startswith("report:"))
async def cb_report_period(callback: CallbackQuery) -> None:
    try:
        days = int((callback.data or "report:7").split(":")[1])
    except ValueError:
        days = 7
    await _render_report(callback, days)


# ── Настройки: автономия ──────────────────────────────────────────────────────
def _settings_text(level: str) -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        "<b>Автономия ИИ</b> — насколько ассистент действует сам:\n"
        f"Сейчас: <b>{AUTONOMY_TITLES.get(level, level)}</b>\n\n"
        "Ещё: <code>/alert 20</code> — алерт по марже, "
        "<code>/subscribe</code> — регулярные отчёты."
    )


@router.callback_query(F.data == "menu:settings")
async def cb_settings(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    async with session_factory() as session:
        level = await agent.get_autonomy(session, callback.from_user.id)
    await _edit(callback, _settings_text(level), settings_kb(level))


@router.callback_query(F.data.startswith("auto:"))
async def cb_set_autonomy(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return
    level = (callback.data or "auto:semi").split(":")[1]
    if level not in agent.AUTONOMY_LEVELS:
        await callback.answer()
        return
    async with session_factory() as session:
        await agent.set_autonomy(session, callback.from_user.id, level)
    await _edit(callback, _settings_text(level), settings_kb(level))


# ── Разделы-справки (соцсети, маркетплейс, таблицы) ───────────────────────────
@router.callback_query(F.data.startswith("menu:"))
async def cb_section(callback: CallbackQuery) -> None:
    section = (callback.data or "").split(":", 1)[1]
    text = SECTION_HELP.get(section)
    if text:
        await _edit(callback, text, back_menu())
    else:
        await callback.answer()
