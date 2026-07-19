from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import User
from wareon.keyboards import (
    back_menu,
    features_kb,
    main_menu,
    onboarding_kb,
    panel_period_kb,
    report_kb,
    settings_kb,
)
from wareon.services import agent, reports
from wareon.services.metrics import build_panel

router = Router(name="start")

# ── Тексты (единый голос: коротко, на «ты», по делу) ─────────────────────────
MENU = (
    "<b>Wareon</b> — ИИ-ассистент твоего бизнеса.\n"
    "Вижу цифры, нахожу рост и узкие места, подсказываю шаг.\n\n"
    "Выбирай 👇"
)

DASHBOARD_HINT = "\n\n✨ «Открыть дашборд» — вся глубина в одном экране."


def welcome_text() -> str:
    return MENU + (DASHBOARD_HINT if settings.webapp_enabled else "")


ONBOARDING = (
    "👋 Привет! Я <b>Wareon</b> — твой ИИ бизнес-ассистент.\n\n"
    "Я не «ещё одна табличка». Я смотрю на твои цифры, сам нахожу "
    "<b>точки роста</b> и <b>узкие места</b> и говорю, что делать — прямо здесь, "
    "в Telegram.\n\n"
    "Познакомимся за минуту?"
)

FEATURES = (
    "<b>Что я умею</b>\n\n"
    "🎛 <b>Пульт</b> — вся аналитика: прибыль, маржа, тренды, прогноз.\n"
    "🧠 <b>Ассистент</b> — спроси что угодно, разберу твои данные и подскажу.\n"
    "🧮 <b>Калькуляторы</b> — юнит-экономика, ROI, зарплаты за пару кликов.\n"
    "📋 <b>Отчёты</b> — регулярные сводки и алерты по марже.\n"
    "📣 <b>Соцсети</b> — статистика каналов и групп.\n\n"
    "Чем больше данных дашь — тем точнее веду. Начнём с первой цифры."
)

AGENT_CARD = (
    "🧠 <b>Ассистент</b>\n\n"
    "Задай вопрос или дай задачу — посмотрю данные и отвечу по делу.\n\n"
    "<i>Например:</i>\n"
    "• как дела за неделю?\n"
    "• где я теряю деньги?\n"
    "• заведи метрику доли рекламы\n\n"
    "Пиши <code>/agent …</code> — или просто сообщением."
)

SALE_CARD = (
    "➕ <b>Записать продажу</b>\n\n"
    "<code>/sale выручка себестоимость источник</code>\n"
    "Пример: <code>/sale 15000 8000 сайт</code>\n\n"
    "Пару продаж — и жми 🎛 <b>Пульт</b>, покажу тренды."
)

SECTION_HELP = {
    "social": (
        "📣 <b>Соцсети</b>\n\n"
        "Добавь меня в канал или группу администратором — начну считать посты, "
        "сообщения, подписки и отписки.\n\n"
        "• В группе — <code>/stats</code>\n"
        "• Здесь — <code>/channels</code>, список подключённых чатов\n\n"
        "<i>Другие соцсети — на подходе.</i>"
    ),
    "tables": (
        "📑 <b>Умные таблицы</b>\n\n"
        "Пришли файл <b>.xlsx</b> или <b>.csv</b> — разберу структуру, посчитаю "
        "суммы и средние, найду топ и пустые ячейки.\n\n"
        "Потом спрашивай текстом: «сумма выручки», «топ товаров».\n\n"
        "<code>/tables</code> — история загрузок"
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


# ── /start и онбординг ────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    is_new = True
    if message.from_user:
        async with session_factory() as session:
            exists = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
            is_new = exists is None
            if is_new:
                session.add(User(tg_id=message.from_user.id, username=message.from_user.username))
                await session.commit()
    if is_new:
        await message.answer(ONBOARDING, reply_markup=onboarding_kb())
    else:
        await message.answer(welcome_text(), reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(FEATURES, reply_markup=main_menu())


@router.callback_query(F.data == "onb:features")
async def cb_features(callback: CallbackQuery) -> None:
    await _edit(callback, FEATURES, features_kb())


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
    from wareon.handlers.pulse import PULSE_EMPTY, format_panel

    if callback.from_user is None:
        return
    async with session_factory() as session:
        panel = await build_panel(session, callback.from_user.id, days=days)
    revenue = next((m for m in panel.metrics if m.key == "revenue"), None)
    text = PULSE_EMPTY if (revenue is None or not revenue.value) else format_panel(panel)
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
            "📋 <b>Отчёт</b>\n\nПродаж пока нет. Запиши первую — "
            "и я соберу сводку.\n\n➕ <code>/sale 15000 8000</code>"
        )
    else:
        text = (
            f"📋 <b>Отчёт · {days} дн</b>\n\n{reports.format_summary(summary)}\n\n"
            "🗓 Авто-сводки: <code>/subscribe daily 09:00</code> · "
            "алерт: <code>/alert 20</code>"
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
        "<b>Автономия ассистента</b> — насколько я действую сам:\n"
        f"Сейчас — <b>{AUTONOMY_TITLES.get(level, level)}</b>\n\n"
        "Ещё: <code>/alert 20</code> — алерт по марже · "
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


# ── Разделы-справки (соцсети, таблицы) ────────────────────────────────────────
@router.callback_query(F.data.in_({"menu:social", "menu:tables"}))
async def cb_section(callback: CallbackQuery) -> None:
    section = (callback.data or "").split(":", 1)[1]
    text = SECTION_HELP.get(section)
    if text:
        await _edit(callback, text, back_menu())
    else:
        await callback.answer()
