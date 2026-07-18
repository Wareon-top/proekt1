from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import User
from wareon.keyboards import BACK_TO_MENU, main_menu

router = Router(name="start")

WELCOME = (
    "👋 Привет! Я <b>Wareon Analytics</b> — система аналитики нового поколения.\n\n"
    "Я помогаю не просто считать цифры, а <b>принимать решения</b>:\n"
    "• бизнес-аналитика: продажи, конверсия, выручка, зарплаты\n"
    "• аналитика каналов и групп Telegram\n"
    "• аналитика карточек на маркетплейсах\n"
    "• умные таблицы — пришлите файл, я разберу\n"
    "• отчёты с графиками и рекомендациями\n"
    "• 🧠 ИИ-сводка и ассистент: <code>/brief</code> и <code>/ask вопрос</code>\n"
)

DASHBOARD_HINT = "\n✨ «Открыть дашборд» — вся аналитика в одном визуальном экране.\n"


def welcome_text() -> str:
    tail = DASHBOARD_HINT if settings.webapp_enabled else "\n"
    return WELCOME + tail + "Выберите направление:"

SECTION_HELP = {
    "business": (
        "📊 <b>Бизнес-аналитика</b>\n\n"
        "<code>/sale 15000 8000 сайт</code> — записать продажу "
        "(выручка, себестоимость, источник)\n"
        "<code>/profit 100000 60000</code> — прибыль, маржа, наценка\n"
        "<code>/conversion 1000 37</code> — конверсия (посетители, покупки)\n"
        "<code>/avg 150000 42</code> — средний чек (выручка, заказы)\n"
        "<code>/roi 50000 200000</code> — ROI (прибыль, вложения)\n"
        "<code>/romi 300000 100000</code> — ROMI (доход с рекламы, бюджет)\n"
        "<code>/breakeven 100000 1500 900</code> — точка безубыточности "
        "(пост. затраты, цена, перем. затраты)\n"
        "<code>/salary 50000 800000 5 10000</code> — зарплата "
        "(оклад, объём продаж, %, бонус)\n"
        "<code>/funnel показы:10000 клики:800 заказы:56</code> — воронка продаж"
    ),
    "social": (
        "📣 <b>Аналитика соцсетей</b>\n\n"
        "1. Добавьте меня в канал или группу (администратором)\n"
        "2. Я начну собирать статистику: сообщения, посты, подписки, отписки\n"
        "3. В группе — команда <code>/stats</code>\n"
        "4. Здесь, в личке — <code>/channels</code>, чтобы посмотреть все подключённые чаты\n\n"
        "Подключение других соцсетей — в разработке."
    ),
    "marketplace": (
        "🛍 <b>Аналитика маркетплейсов</b>\n\n"
        "Для дизайнеров карточек и менеджеров:\n"
        "<code>/card 50000 2500 400 120</code> — воронка карточки "
        "(показы, клики, корзины, заказы)\n"
        "<code>/card 50000 2500 400 120 30000 180000</code> — то же + ДРР "
        "(расходы на рекламу, выручка)\n"
        "<code>/unit 1500 20 80 600 50</code> — юнит-экономика "
        "(цена, комиссия %, логистика, себестоимость, реклама на ед.)"
    ),
    "tables": (
        "📑 <b>Умные таблицы</b>\n\n"
        "Просто пришлите мне файл <b>.xlsx</b> или <b>.csv</b> — "
        "я разберу структуру, посчитаю суммы и средние по числовым столбцам, "
        "найду топ-категории и пустые ячейки.\n\n"
        "После загрузки задавайте вопросы обычным текстом:\n"
        "• «сумма выручки»\n"
        "• «топ товаров по выручке»\n"
        "• «какой товар принёс больше всего?»\n\n"
        "<code>/tables</code> — история загруженных таблиц"
    ),
    "reports": (
        "📋 <b>Отчёты</b>\n\n"
        "<code>/report</code> — отчёт по продажам за 7 дней\n"
        "<code>/report 30</code> — за 30 дней\n\n"
        "В отчёте: выручка, прибыль, маржа, средний чек, сравнение с прошлым "
        "периодом (▲/▼), лучший день недели, разбивка по источникам, график "
        "и рекомендация, что делать дальше.\n\n"
        "Автоматически (время МСК):\n"
        "<code>/subscribe daily 09:00</code> — отчёт каждое утро\n"
        "<code>/subscribe weekly 10:00</code> — по понедельникам\n"
        "<code>/unsubscribe</code> — отключить\n"
        "<code>/alert 20</code> — предупреждать, если маржа за сутки ниже 20%"
    ),
}


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user:
        async with session_factory() as session:
            exists = await session.scalar(
                select(User).where(User.tg_id == message.from_user.id)
            )
            if not exists:
                session.add(
                    User(tg_id=message.from_user.id, username=message.from_user.username)
                )
                await session.commit()
    await message.answer(welcome_text(), reply_markup=main_menu())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(welcome_text(), reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("menu:"))
async def cb_section(callback: CallbackQuery) -> None:
    section = (callback.data or "").split(":", 1)[1]
    text = SECTION_HELP.get(section)
    if text and isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=BACK_TO_MENU)
    await callback.answer()
