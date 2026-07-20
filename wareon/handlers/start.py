from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import User
from wareon.keyboards import (
    agent_card_kb,
    features_kb,
    main_menu,
    onboarding_kb,
    report_kb,
    sale_card_kb,
    settings_kb,
    social_card_kb,
    tables_card_kb,
)
from wareon.services import agent, branding, reports

router = Router(name="start")

# ── Тексты (единый голос: коротко, на «ты», по делу) ─────────────────────────
MENU = (
    "<b>Главное меню</b>\n"
    "Вижу цифры, нахожу рост и узкие места, подсказываю шаг.\n\n"
    "Выбирай ниже 👇"
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
    "Выбери готовый вопрос кнопкой — или напиши свой сообщением "
    "(<code>/agent …</code> или просто текстом)."
)

SALE_CARD = (
    "➕ <b>Записать продажу</b>\n\n"
    "Жми <b>«Ввести пошагово»</b> — проведу по шагам.\n"
    "Или командой: <code>/sale 15000 8000 сайт</code>"
)

SECTION_HELP = {
    "social": (
        "📣 <b>Соцсети</b>\n\n"
        "Добавь меня в канал или группу администратором — начну считать посты, "
        "сообщения, подписки и отписки.\n\n"
        "• В группе — <code>/stats</code>\n"
        "• Здесь — «Подключённые чаты» ниже\n\n"
        "<i>Другие соцсети — на подходе.</i>"
    ),
    "tables": (
        "📑 <b>Таблицы</b>\n\n"
        "🗂 <b>Таблица клиентов (CRM)</b> — веди лидов и заказы прямо здесь: "
        "статусы, дедлайны, суммы, воронка. Открывается кнопкой ниже.\n\n"
        "📥 Или пришли файл <b>.xlsx / .csv</b> — разберу и заведу данные в аналитику."
    ),
}

AUTONOMY_TITLES = {
    "autopilot": "🟢 Автопилот — делаю всё сам",
    "semi": "🟡 Полу-автоном — рутину сам, важное с подтверждением",
    "manual": "🔴 Ручной — только предлагаю",
}


# ── Брендовая карточка меню (баннер-шапка + подпись + кнопки) ─────────────────
def _banner() -> BufferedInputFile:
    return BufferedInputFile(branding.menu_banner_png(), "wareon.png")


async def _send_card(message: Message, caption: str, markup) -> None:
    await message.answer_photo(_banner(), caption=caption, reply_markup=markup)


async def _edit_card(callback: CallbackQuery, caption: str, markup) -> None:
    """Меняет подпись брендовой карточки на месте; если нельзя — шлёт новую."""
    msg = callback.message
    if isinstance(msg, Message):
        try:
            await msg.edit_caption(caption=caption, reply_markup=markup)
        except Exception:
            await msg.answer_photo(_banner(), caption=caption, reply_markup=markup)
    await callback.answer()


async def _text_out(callback: CallbackQuery, text: str, markup) -> None:
    """Отдельное текстовое сообщение (отчёт) — не подпись под баннером."""
    msg = callback.message
    if isinstance(msg, Message):
        try:
            await msg.edit_text(text, reply_markup=markup)
        except Exception:
            await msg.answer(text, reply_markup=markup)
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
        await _send_card(message, ONBOARDING, onboarding_kb())
    else:
        await _send_card(message, welcome_text(), main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await _send_card(message, FEATURES, main_menu())


@router.callback_query(F.data == "onb:features")
async def cb_features(callback: CallbackQuery) -> None:
    await _edit_card(callback, FEATURES, features_kb())


@router.callback_query(F.data == "menu:main")
async def cb_main(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await _send_card(callback.message, welcome_text(), main_menu())
    await callback.answer()


@router.callback_query(F.data == "menu:agent")
async def cb_agent_card(callback: CallbackQuery) -> None:
    await _edit_card(callback, AGENT_CARD, agent_card_kb())


@router.callback_query(F.data == "menu:sale")
async def cb_sale_card(callback: CallbackQuery) -> None:
    await _edit_card(callback, SALE_CARD, sale_card_kb())


# (Пульт обрабатывает handlers/pulse.py — фото-график + подпись)


# ── Отчёт ─────────────────────────────────────────────────────────────────────
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
    await _text_out(callback, text, report_kb())


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
    await _edit_card(callback, _settings_text(level), settings_kb(level))


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
    await _edit_card(callback, _settings_text(level), settings_kb(level))


# ── Разделы-справки (соцсети, таблицы) ────────────────────────────────────────
@router.callback_query(F.data.in_({"menu:social", "menu:tables"}))
async def cb_section(callback: CallbackQuery) -> None:
    section = (callback.data or "").split(":", 1)[1]
    text = SECTION_HELP.get(section)
    if not text:
        await callback.answer()
        return
    markup = social_card_kb() if section == "social" else tables_card_kb()
    await _edit_card(callback, text, markup)
