"""Отчёты: агрегация продаж за период, рекомендации и график выручки."""

import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.db.models import Sale


@dataclass
class SalesSummary:
    days: int
    orders: int
    revenue: float
    cost: float
    profit: float
    margin_pct: float
    average_check: float
    by_source: dict[str, float]
    by_day: dict[str, float]


async def sales_summary(session: AsyncSession, user_tg_id: int, days: int = 7) -> SalesSummary:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.scalars(
            select(Sale).where(Sale.user_tg_id == user_tg_id, Sale.created_at >= since)
        )
    ).all()

    revenue = sum(s.revenue for s in rows)
    cost = sum(s.cost for s in rows)
    profit = revenue - cost
    by_source: dict[str, float] = {}
    by_day: dict[str, float] = {}
    for s in rows:
        src = s.source or "не указан"
        by_source[src] = by_source.get(src, 0.0) + s.revenue
        day = s.created_at.strftime("%d.%m")
        by_day[day] = by_day.get(day, 0.0) + s.revenue

    return SalesSummary(
        days=days,
        orders=len(rows),
        revenue=round(revenue, 2),
        cost=round(cost, 2),
        profit=round(profit, 2),
        margin_pct=round(profit / revenue * 100, 2) if revenue else 0.0,
        average_check=round(revenue / len(rows), 2) if rows else 0.0,
        by_source=by_source,
        by_day=dict(sorted(by_day.items())),
    )


def format_summary(s: SalesSummary) -> str:
    lines = [
        f"📋 Отчёт по продажам за {s.days} дн.",
        "",
        f"🛒 Заказов: {s.orders}",
        f"💰 Выручка: {s.revenue:,.2f} ₽",
        f"📦 Себестоимость: {s.cost:,.2f} ₽",
        f"📈 Прибыль: {s.profit:,.2f} ₽ (маржа {s.margin_pct}%)",
        f"🧾 Средний чек: {s.average_check:,.2f} ₽",
    ]
    if s.by_source:
        lines.append("")
        lines.append("Источники выручки:")
        for src, rev in sorted(s.by_source.items(), key=lambda kv: -kv[1]):
            share = rev / s.revenue * 100 if s.revenue else 0
            lines.append(f"• {src}: {rev:,.2f} ₽ ({share:.1f}%)")
    lines.append("")
    lines.append(recommendation(s))
    return "\n".join(lines)


def recommendation(s: SalesSummary) -> str:
    """Простая рекомендация для принятия решения на основе сводки."""
    if s.orders == 0:
        return "💡 Данных за период нет. Добавьте продажи командой /sale — и я начну считать."
    if s.margin_pct < 15:
        return (
            "💡 Маржа ниже 15% — бизнес уязвим. Стоит пересмотреть цены "
            "или снизить себестоимость."
        )
    if s.by_source and len(s.by_source) >= 2:
        top_src, top_rev = max(s.by_source.items(), key=lambda kv: kv[1])
        if s.revenue and top_rev / s.revenue > 0.7:
            return (
                f"💡 Более 70% выручки даёт один источник «{top_src}» — это риск. "
                "Диверсифицируйте каналы продаж."
            )
    return "💡 Показатели здоровые. Следите за динамикой среднего чека и маржи."


def revenue_chart_png(s: SalesSummary) -> bytes | None:
    """PNG-график выручки по дням; None, если данных меньше двух точек."""
    if len(s.by_day) < 2:
        return None
    days = list(s.by_day.keys())
    values = list(s.by_day.values())

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.bar(days, values, color="#4C72B0")
    ax.set_title(f"Выручка по дням (последние {s.days} дн.)")
    ax.set_ylabel("₽")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
