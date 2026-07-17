"""Отчёты: агрегация продаж, сравнение периодов, рекомендации и график выручки."""

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.db.models import Sale

WEEKDAYS_RU = [
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
]


def delta_pct(current: float, prev: float) -> float | None:
    """Изменение в % к прошлому периоду; None, если сравнивать не с чем."""
    if not prev:
        return None
    return round((current - prev) / prev * 100, 2)


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
    # сравнение с предыдущим периодом той же длины
    prev_orders: int = 0
    prev_revenue: float = 0.0
    revenue_delta_pct: float | None = None
    orders_delta_pct: float | None = None
    avg_check_delta_pct: float | None = None
    margin_delta_pp: float | None = None  # изменение маржи в процентных пунктах
    best_weekday: str | None = None


async def sales_summary(session: AsyncSession, user_tg_id: int, days: int = 7) -> SalesSummary:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    prev_since = now - timedelta(days=days * 2)

    rows = (
        await session.scalars(
            select(Sale).where(Sale.user_tg_id == user_tg_id, Sale.created_at >= since)
        )
    ).all()
    prev_rows = (
        await session.scalars(
            select(Sale).where(
                Sale.user_tg_id == user_tg_id,
                Sale.created_at >= prev_since,
                Sale.created_at < since,
            )
        )
    ).all()

    revenue = sum(s.revenue for s in rows)
    cost = sum(s.cost for s in rows)
    profit = revenue - cost
    margin = profit / revenue * 100 if revenue else 0.0
    avg_check = revenue / len(rows) if rows else 0.0

    prev_revenue = sum(s.revenue for s in prev_rows)
    prev_cost = sum(s.cost for s in prev_rows)
    prev_margin = (prev_revenue - prev_cost) / prev_revenue * 100 if prev_revenue else None
    prev_avg = prev_revenue / len(prev_rows) if prev_rows else 0.0

    by_source: dict[str, float] = {}
    by_day: dict[str, float] = {}
    by_weekday: dict[int, float] = {}
    for s in rows:
        src = s.source or "не указан"
        by_source[src] = by_source.get(src, 0.0) + s.revenue
        day = s.created_at.strftime("%d.%m")
        by_day[day] = by_day.get(day, 0.0) + s.revenue
        wd = s.created_at.weekday()
        by_weekday[wd] = by_weekday.get(wd, 0.0) + s.revenue

    best_weekday = None
    if len(by_day) >= 7 and revenue:
        best_weekday = WEEKDAYS_RU[max(by_weekday, key=lambda k: by_weekday[k])]

    return SalesSummary(
        days=days,
        orders=len(rows),
        revenue=round(revenue, 2),
        cost=round(cost, 2),
        profit=round(profit, 2),
        margin_pct=round(margin, 2),
        average_check=round(avg_check, 2),
        by_source=by_source,
        by_day=dict(sorted(by_day.items())),
        prev_orders=len(prev_rows),
        prev_revenue=round(prev_revenue, 2),
        revenue_delta_pct=delta_pct(revenue, prev_revenue),
        orders_delta_pct=delta_pct(len(rows), len(prev_rows)),
        avg_check_delta_pct=delta_pct(avg_check, prev_avg),
        margin_delta_pp=round(margin - prev_margin, 2) if prev_margin is not None else None,
        best_weekday=best_weekday,
    )


def _fmt_delta(d: float | None, unit: str = "%") -> str:
    if d is None:
        return ""
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "•")
    return f"  {arrow} {d:+.1f}{unit}"


def format_summary(s: SalesSummary) -> str:
    lines = [
        f"📋 Отчёт по продажам за {s.days} дн.",
        "",
        f"🛒 Заказов: {s.orders}{_fmt_delta(s.orders_delta_pct)}",
        f"💰 Выручка: {s.revenue:,.2f} ₽{_fmt_delta(s.revenue_delta_pct)}",
        f"📦 Себестоимость: {s.cost:,.2f} ₽",
        f"📈 Прибыль: {s.profit:,.2f} ₽ (маржа {s.margin_pct}%"
        + (f", {s.margin_delta_pp:+.1f} п.п." if s.margin_delta_pp is not None else "")
        + ")",
        f"🧾 Средний чек: {s.average_check:,.2f} ₽{_fmt_delta(s.avg_check_delta_pct)}",
    ]
    if s.revenue_delta_pct is not None:
        lines.append(
            f"\n↔️ Прошлый период: {s.prev_orders} заказов, {s.prev_revenue:,.2f} ₽"
        )
    if s.by_source:
        lines.append("")
        lines.append("Источники выручки:")
        for src, rev in sorted(s.by_source.items(), key=lambda kv: -kv[1]):
            share = rev / s.revenue * 100 if s.revenue else 0
            lines.append(f"• {src}: {rev:,.2f} ₽ ({share:.1f}%)")
    if s.best_weekday:
        lines.append("")
        lines.append(f"📅 Больше всего выручки приносит {s.best_weekday}.")
    lines.append("")
    lines.append(recommendation(s))
    return "\n".join(lines)


def recommendation(s: SalesSummary) -> str:
    """Рекомендация для принятия решения на основе сводки и динамики."""
    if s.orders == 0:
        return "💡 Данных за период нет. Добавьте продажи командой /sale — и я начну считать."
    if s.revenue_delta_pct is not None and s.revenue_delta_pct <= -20:
        return (
            f"💡 Выручка упала на {abs(s.revenue_delta_pct):.0f}% к прошлому периоду. "
            "Разберитесь, какой источник просел (/report) и усильте его в первую очередь."
        )
    if s.margin_pct < 15:
        return (
            "💡 Маржа ниже 15% — бизнес уязвим. Стоит пересмотреть цены "
            "или снизить себестоимость."
        )
    if s.margin_delta_pp is not None and s.margin_delta_pp <= -5:
        return (
            f"💡 Маржа снизилась на {abs(s.margin_delta_pp):.1f} п.п. — растёт "
            "себестоимость или пошли скидки. Проверьте структуру затрат."
        )
    if s.by_source and len(s.by_source) >= 2:
        top_src, top_rev = max(s.by_source.items(), key=lambda kv: kv[1])
        if s.revenue and top_rev / s.revenue > 0.7:
            return (
                f"💡 Более 70% выручки даёт один источник «{top_src}» — это риск. "
                "Диверсифицируйте каналы продаж."
            )
    if s.revenue_delta_pct is not None and s.revenue_delta_pct >= 20:
        return (
            f"💡 Рост выручки {s.revenue_delta_pct:+.0f}% — отличный темп! "
            "Убедитесь, что хватит запасов и мощностей, чтобы его удержать."
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
