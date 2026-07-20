"""ИИ-слой Wareon: сводка и ассистент на Claude.

«Обучение» Клода = роль (системный промпт) + база знаний + реальные данные
клиента, поданные в контекст. Модель не дообучается.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.config import settings
from wareon.db.models import AgentMemory, AiBrief
from wareon.services import reports
from wareon.services.knowledge import BUSINESS_KNOWLEDGE
from wareon.services.metrics import build_panel

logger = logging.getLogger(__name__)

ROLE = """\
Ты — Wareon, ИИ бизнес-аналитик. Твоя задача не просто считать цифры,
а помогать предпринимателю принимать решения.

Правила общения:
- Пиши коротко, по-деловому, на русском. Без воды и общих фраз.
- Опирайся только на предоставленные цифры клиента. Не выдумывай данные.
  Если данных мало — честно скажи об этом.
- Советы давай в формате рецепта: Симптом → Причина → Действие.
- Обращайся на «ты», дружелюбно, но по существу.
"""

DISABLED_MSG = (
    "🤖 ИИ пока не подключён. Нужен API-ключ Anthropic (переменная "
    "ANTHROPIC_API_KEY). Как заведёшь — сводка и ассистент заработают."
)
ERROR_MSG = "🤖 Не удалось получить ответ ИИ. Попробуйте чуть позже."
NO_DATA_MSG = (
    "🤖 Пока нет данных для анализа. Пришлите таблицу продаж боту "
    "или добавьте продажи командой /sale — и я подготовлю сводку."
)


def system_prompt() -> str:
    return ROLE + "\n\n" + BUSINESS_KNOWLEDGE


def _num(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def build_context(summary: reports.SalesSummary, net_today: float) -> str:
    """Компактная выжимка реальных цифр клиента для подачи модели."""
    lines = [
        f"Период: последние {summary.days} дн.",
        f"Заработано чистыми сегодня: {_num(net_today)} ₽",
        f"Выручка: {_num(summary.revenue)} ₽; себестоимость: {_num(summary.cost)} ₽; "
        f"прибыль: {_num(summary.profit)} ₽; маржа: {summary.margin_pct}%.",
        f"Заказов: {summary.orders}; средний чек: {_num(summary.average_check)} ₽.",
    ]
    if summary.revenue_delta_pct is not None:
        lines.append(f"Выручка к прошлому периоду: {summary.revenue_delta_pct:+.1f}%.")
    if summary.margin_delta_pp is not None:
        lines.append(f"Маржа к прошлому периоду: {summary.margin_delta_pp:+.1f} п.п.")
    if summary.best_weekday:
        lines.append(f"Лучший день недели по выручке: {summary.best_weekday}.")
    if summary.by_source:
        src = ", ".join(f"{k}: {_num(v)} ₽" for k, v in summary.by_source.items())
        lines.append(f"Выручка по источникам: {src}.")
    if summary.by_product:
        top = sorted(summary.by_product.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines.append("Прибыль по товарам: " + ", ".join(f"{k}: {_num(v)} ₽" for k, v in top) + ".")
    return "\n".join(lines)


async def _call_claude(system: str, user: str, max_tokens: int = 1200) -> str:
    from anthropic import AsyncAnthropic  # ленивый импорт — бот работает и без пакета

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.ai_model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _panel_context(panel) -> str:
    """Добавляет к контексту точки роста / узкие места / прогноз из движка метрик."""
    parts = []
    growth = [m.title for m in panel.growth_points]
    bottleneck = [m.title for m in panel.bottlenecks]
    if growth:
        parts.append("Точки роста: " + ", ".join(growth) + ".")
    if bottleneck:
        parts.append("Узкие места: " + ", ".join(bottleneck) + ".")
    if panel.forecast_revenue is not None:
        parts.append(f"Прогноз выручки на 7 дн: {_num(panel.forecast_revenue)} ₽.")
    return ("\n" + " ".join(parts)) if parts else ""


async def _memory_context(session: AsyncSession, user_tg_id: int) -> str:
    facts = (
        await session.scalars(
            select(AgentMemory)
            .where(AgentMemory.user_tg_id == user_tg_id)
            .order_by(AgentMemory.created_at.desc())
            .limit(15)
        )
    ).all()
    if not facts:
        return ""
    return "\n\nЧто помню о бизнесе: " + "; ".join(f.content for f in reversed(facts)) + "."


async def daily_brief(session: AsyncSession, user_tg_id: int) -> str:
    """Утренняя сводка: итоги + приоритеты + рецепты. Кэш — раз в сутки."""
    if not settings.ai_enabled:
        return DISABLED_MSG
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cached = await session.scalar(
        select(AiBrief).where(AiBrief.user_tg_id == user_tg_id, AiBrief.day == today)
    )
    if cached:
        return cached.content

    summary = await reports.sales_summary(session, user_tg_id, 7)
    if summary.orders == 0:
        return NO_DATA_MSG
    net_today = await reports.today_profit(session, user_tg_id)
    panel = await build_panel(session, user_tg_id, 7)
    memory = await _memory_context(session, user_tg_id)

    user_msg = (
        "Данные бизнеса клиента:\n"
        + build_context(summary, net_today)
        + _panel_context(panel)
        + memory
        + "\n\nСоставь короткую утреннюю сводку:\n"
        "1) одна строка — как идут дела (главный итог);\n"
        "2) 3 приоритета на сегодня (нумерованный список, каждый — рецепт "
        "Симптом → Причина → Действие);\n"
        "Всего не больше 12 строк."
    )
    try:
        text = await _call_claude(system_prompt(), user_msg, 1200)
    except Exception:
        logger.exception("AI brief failed for %s", user_tg_id)
        return ERROR_MSG

    session.add(AiBrief(user_tg_id=user_tg_id, day=today, content=text))
    await session.commit()
    return text


async def ask(session: AsyncSession, user_tg_id: int, question: str) -> str:
    """ИИ-ассистент: отвечает на вопрос по реальным данным клиента."""
    if not settings.ai_enabled:
        return DISABLED_MSG
    summary = await reports.sales_summary(session, user_tg_id, 30)
    net_today = await reports.today_profit(session, user_tg_id)
    ctx = build_context(summary, net_today) if summary.orders else "Данных о продажах пока нет."

    user_msg = (
        f"Данные бизнеса клиента:\n{ctx}\n\n"
        f"Вопрос клиента: {question}\n\n"
        "Ответь коротко и по делу, опираясь на цифры. Если по вопросу видно "
        "проблему — дай рецепт Симптом → Причина → Действие."
    )
    try:
        return await _call_claude(system_prompt(), user_msg, 1000)
    except Exception:
        logger.exception("AI ask failed for %s", user_tg_id)
        return ERROR_MSG
