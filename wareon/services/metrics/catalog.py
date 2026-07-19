"""Каталог встроенных метрик — «максимум показателей» по областям.

Каждая метрика — формула над базовыми переменными (см. panel.base_variables).
Метрики, которым нужны данные вне продаж (реклама, визиты), считаются, когда эти
цифры донесены вручную (гибрид из конституции); без них показываются как «нет
данных». Каталог собирается один раз при импорте — это дёшево и быстро.
"""

from dataclasses import dataclass

# Области метрик (для группировки в «пульте»).
AREA_FINANCE = "finance"
AREA_SALES = "sales"
AREA_MARKETING = "marketing"
AREA_MARKETPLACE = "marketplace"
AREA_CLIENTS = "clients"

AREA_TITLES = {
    AREA_FINANCE: "Финансы",
    AREA_SALES: "Продажи и конверсия",
    AREA_MARKETING: "Маркетинг",
    AREA_MARKETPLACE: "Маркетплейс",
    AREA_CLIENTS: "Клиентская экономика",
    "custom": "Мои метрики",
}


@dataclass(frozen=True)
class MetricDef:
    """Определение метрики. direction: up — хорошо, когда растёт; down — хорошо,
    когда падает; neutral — просто факт (без оценки роста/узкого места)."""

    key: str
    title: str
    expr: str
    unit: str
    direction: str  # up | down | neutral
    area: str


# Базовые переменные, доступные формулам (задаёт panel.base_variables):
#   revenue  — выручка за период
#   cost     — себестоимость за период
#   profit   — прибыль (revenue - cost)
#   orders   — число продаж
#   days     — длина периода в днях
#   ad_spend — рекламные расходы (ручной ввод; иначе метрика «нет данных»)
#   visitors — визиты/трафик (ручной ввод)
BUILTIN_METRICS: list[MetricDef] = [
    # Финансы
    MetricDef("revenue", "Выручка", "revenue", "₽", "up", AREA_FINANCE),
    MetricDef("cost", "Себестоимость", "cost", "₽", "down", AREA_FINANCE),
    MetricDef("profit", "Прибыль", "revenue - cost", "₽", "up", AREA_FINANCE),
    MetricDef("margin_pct", "Маржа", "(revenue - cost) / revenue * 100", "%", "up", AREA_FINANCE),
    MetricDef("markup_pct", "Наценка", "(revenue - cost) / cost * 100", "%", "up", AREA_FINANCE),
    # Продажи и конверсия
    MetricDef("orders", "Заказов", "orders", "шт", "up", AREA_SALES),
    MetricDef("avg_check", "Средний чек", "revenue / orders", "₽", "up", AREA_SALES),
    MetricDef("revenue_per_day", "Выручка в день", "revenue / days", "₽", "up", AREA_SALES),
    MetricDef("orders_per_day", "Заказов в день", "orders / days", "шт", "up", AREA_SALES),
    MetricDef("conversion_pct", "Конверсия", "orders / visitors * 100", "%", "up", AREA_SALES),
    # Маркетинг
    MetricDef("drr_pct", "ДРР (доля рекламы)", "ad_spend / revenue * 100", "%", "down", AREA_MARKETING),
    MetricDef("romi_pct", "ROMI", "(revenue - ad_spend) / ad_spend * 100", "%", "up", AREA_MARKETING),
    MetricDef("ad_share_profit", "Реклама к прибыли", "ad_spend / profit * 100", "%", "down", AREA_MARKETING),
    # Клиентская экономика
    MetricDef("cac", "CAC (цена заказа)", "ad_spend / orders", "₽", "down", AREA_CLIENTS),
    MetricDef("profit_per_order", "Прибыль с заказа", "(revenue - cost) / orders", "₽", "up", AREA_CLIENTS),
]

_BY_KEY = {m.key: m for m in BUILTIN_METRICS}


def get(key: str) -> MetricDef | None:
    return _BY_KEY.get(key)


def by_area() -> dict[str, list[MetricDef]]:
    """Метрики, сгруппированные по областям (в порядке объявления)."""
    grouped: dict[str, list[MetricDef]] = {}
    for m in BUILTIN_METRICS:
        grouped.setdefault(m.area, []).append(m)
    return grouped
