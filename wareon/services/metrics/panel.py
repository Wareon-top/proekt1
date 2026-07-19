"""Сборка «пульта»: считает метрики из данных клиента, сравнивает с прошлым
периодом (тренд) и помечает точки роста / узкие места. Плюс простой прогноз.

Скорость: базовые агрегаты берём одним SQL-проходом (SUM/COUNT), а не тянем строки
в Python; формулы компилируются и кэшируются в движке формул."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.db.models import CustomMetric, Sale
from wareon.services.metrics import catalog
from wareon.services.metrics.catalog import MetricDef
from wareon.services.metrics.formula import evaluate

# Порог значимости тренда: меньше — считаем «без изменений».
TREND_SIGNIFICANT_PCT = 5.0

STATUS_GROWTH = "growth"  # 📈 точка роста
STATUS_BOTTLENECK = "bottleneck"  # ⚠️ узкое место
STATUS_FLAT = "flat"  # без заметных изменений
STATUS_NA = "na"  # нет данных для расчёта


@dataclass
class MetricValue:
    key: str
    title: str
    unit: str
    area: str
    value: float | None
    prev: float | None
    trend_pct: float | None
    status: str
    custom: bool = False


@dataclass
class Panel:
    days: int
    metrics: list[MetricValue] = field(default_factory=list)
    forecast_revenue: float | None = None  # прогноз выручки на следующие `days` дней

    @property
    def growth_points(self) -> list[MetricValue]:
        return [m for m in self.metrics if m.status == STATUS_GROWTH]

    @property
    def bottlenecks(self) -> list[MetricValue]:
        return [m for m in self.metrics if m.status == STATUS_BOTTLENECK]


async def base_variables(
    session: AsyncSession,
    user_tg_id: int,
    start: datetime,
    end: datetime,
    manual: dict[str, float] | None = None,
) -> dict[str, float]:
    """Базовые переменные из продаж за [start, end) одним запросом."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Sale.revenue), 0.0),
                func.coalesce(func.sum(Sale.cost), 0.0),
                func.count(Sale.id),
            ).where(
                Sale.user_tg_id == user_tg_id,
                Sale.created_at >= start,
                Sale.created_at < end,
            )
        )
    ).one()
    revenue, cost, orders = float(row[0]), float(row[1]), int(row[2])
    days = max(int((end - start).total_seconds() // 86400), 1)
    variables: dict[str, float] = {
        "revenue": revenue,
        "cost": cost,
        "profit": revenue - cost,
        "orders": float(orders),
        "days": float(days),
    }
    if manual:
        variables.update({k: float(v) for k, v in manual.items()})
    return variables


def _trend_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def _status(direction: str, value: float | None, trend_pct: float | None) -> str:
    if value is None:
        return STATUS_NA
    if direction == "neutral" or trend_pct is None:
        return STATUS_FLAT
    # «Хорошее» направление изменения с точки зрения этой метрики.
    good = trend_pct if direction == "up" else -trend_pct
    if good >= TREND_SIGNIFICANT_PCT:
        return STATUS_GROWTH
    if good <= -TREND_SIGNIFICANT_PCT:
        return STATUS_BOTTLENECK
    return STATUS_FLAT


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _metric_value(defn: MetricDef, cur_vars, prev_vars, custom: bool) -> MetricValue:
    value = evaluate(defn.expr, cur_vars)
    prev = evaluate(defn.expr, prev_vars)
    trend = _trend_pct(value, prev)
    return MetricValue(
        key=defn.key,
        title=defn.title,
        unit=defn.unit,
        area=defn.area,
        value=_round(value),
        prev=_round(prev),
        trend_pct=trend,
        status=_status(defn.direction, value, trend),
        custom=custom,
    )


async def _daily_revenue(
    session: AsyncSession, user_tg_id: int, start: datetime, end: datetime
) -> list[float]:
    """Выручка по дням периода (нули для дней без продаж) — для прогноза."""
    rows = (
        await session.execute(
            select(
                func.date(Sale.created_at),
                func.coalesce(func.sum(Sale.revenue), 0.0),
            )
            .where(
                Sale.user_tg_id == user_tg_id,
                Sale.created_at >= start,
                Sale.created_at < end,
            )
            .group_by(func.date(Sale.created_at))
        )
    ).all()
    by_day = {str(d): float(v) for d, v in rows}
    days = max(int((end - start).total_seconds() // 86400), 1)
    series = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        series.append(by_day.get(day, 0.0))
    return series


def linear_forecast(values: list[float], horizon: int) -> float | None:
    """Простой прогноз суммы за следующие `horizon` дней по линейному тренду
    (метод наименьших квадратов). None, если данных мало."""
    n = len(values)
    if n < 2 or horizon <= 0:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        slope = 0.0
    else:
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denom
    intercept = mean_y - slope * mean_x
    total = 0.0
    for i in range(n, n + horizon):
        total += max(slope * i + intercept, 0.0)  # выручка не бывает отрицательной
    return round(total, 2)


async def build_panel(
    session: AsyncSession,
    user_tg_id: int,
    days: int = 7,
    now: datetime | None = None,
    manual: dict[str, float] | None = None,
    include_custom: bool = True,
) -> Panel:
    """Собирает «пульт» за последние `days` дней с трендом к предыдущему периоду."""
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=None) if now.tzinfo else now
    end = now
    start = end - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    cur_vars = await base_variables(session, user_tg_id, start, end, manual)
    prev_vars = await base_variables(session, user_tg_id, prev_start, start, manual)

    metrics = [_metric_value(d, cur_vars, prev_vars, custom=False) for d in catalog.BUILTIN_METRICS]

    if include_custom:
        custom_defs = (
            await session.scalars(
                select(CustomMetric).where(CustomMetric.user_tg_id == user_tg_id)
            )
        ).all()
        for cm in custom_defs:
            defn = MetricDef(cm.key, cm.title, cm.expression, cm.unit, cm.direction, "custom")
            metrics.append(_metric_value(defn, cur_vars, prev_vars, custom=True))

    series = await _daily_revenue(session, user_tg_id, start, end)
    forecast = linear_forecast(series, days)

    return Panel(days=days, metrics=metrics, forecast_revenue=forecast)
