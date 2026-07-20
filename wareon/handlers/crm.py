"""Интеграция CRM-таблицы (Web App) с аналитикой — без отдельного API.

Telegram Web App, запущенный кнопкой reply-клавиатуры, умеет слать данные боту
(sendData → web_app_data). CRM отправляет оплаченные сделки, бот заводит их в
продажи (Sale) — и они появляются в пульте.
"""

import json
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from wareon.config import settings
from wareon.db.base import session_factory
from wareon.db.models import Sale

router = Router(name="crm")
logger = logging.getLogger(__name__)


def _crm_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🗂 Таблица клиентов", web_app=WebAppInfo(url=settings.crm_url))]],
        resize_keyboard=True,
        input_field_placeholder="Открой таблицу кнопкой ниже",
    )


@router.message(Command("crm"))
async def cmd_crm(message: Message) -> None:
    if not settings.webapp_enabled:
        await message.answer(
            "🗂 Таблица клиентов появится, когда подключим дашборд (WEBAPP_URL)."
        )
        return
    await message.answer(
        "🗂 <b>Таблица клиентов</b>\n\n"
        "Открой кнопкой ниже. Внутри жми <b>«📤 В Wareon»</b> — оплаченные сделки "
        "уедут в аналитику и появятся в пульте.",
        reply_markup=_crm_reply_kb(),
    )


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(raw)[:10], fmt)
        except ValueError:
            continue
    return None


def ingest_paid_leads(uid: int, leads: list[dict], now: datetime) -> list[Sale]:
    """Готовит продажи из оплаченных сделок CRM (без записи в БД)."""
    sales: list[Sale] = []
    for lead in leads:
        try:
            amount = float(lead.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        name = (lead.get("name") or "").strip() or None
        created = _parse_date(lead.get("date")) or now
        sales.append(
            Sale(user_tg_id=uid, revenue=amount, cost=0.0, product=name, source="CRM", created_at=created)
        )
    return sales


@router.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    if message.from_user is None or message.web_app_data is None:
        return
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        await message.answer("Не разобрал данные из таблицы.")
        return
    if data.get("type") != "crm_paid":
        return

    leads = data.get("leads") or []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sales = ingest_paid_leads(message.from_user.id, leads, now)
    if not sales:
        await message.answer("Оплаченных сделок с суммой не нашёл — нечего заводить.")
        return

    total = sum(s.revenue for s in sales)
    async with session_factory() as session:
        session.add_all(sales)
        await session.commit()

    await message.answer(
        f"✅ Занёс в аналитику: <b>{len(sales)}</b> оплат на "
        f"<b>{total:,.0f} ₽</b>.\nЖми /pulse — уже в пульте.".replace(",", " ")
    )
