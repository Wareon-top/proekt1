"""Чистые бизнес-расчёты: выручка, прибыль, конверсия, зарплата, юнит-экономика.

Все функции — детерминированные, без побочных эффектов, покрыты тестами.
"""

from dataclasses import dataclass


@dataclass
class ProfitReport:
    revenue: float
    cost: float
    profit: float
    margin_pct: float  # маржинальность, % от выручки
    markup_pct: float  # наценка, % от себестоимости


def profit_report(revenue: float, cost: float) -> ProfitReport:
    if revenue < 0 or cost < 0:
        raise ValueError("Выручка и себестоимость не могут быть отрицательными")
    profit = revenue - cost
    margin = (profit / revenue * 100) if revenue else 0.0
    markup = (profit / cost * 100) if cost else 0.0
    return ProfitReport(revenue, cost, profit, round(margin, 2), round(markup, 2))


def conversion(visitors: int, actions: int) -> float:
    """Конверсия в процентах: сколько посетителей совершили целевое действие."""
    if visitors < 0 or actions < 0:
        raise ValueError("Значения не могут быть отрицательными")
    if actions > visitors:
        raise ValueError("Действий не может быть больше, чем посетителей")
    return round(actions / visitors * 100, 2) if visitors else 0.0


def average_check(revenue: float, orders: int) -> float:
    if orders < 0 or revenue < 0:
        raise ValueError("Значения не могут быть отрицательными")
    return round(revenue / orders, 2) if orders else 0.0


def roi(profit: float, investment: float) -> float:
    """ROI, %: отдача на вложения. Прибыль уже за вычетом вложений."""
    if investment <= 0:
        raise ValueError("Вложения должны быть больше нуля")
    return round(profit / investment * 100, 2)


def romi(ad_revenue: float, ad_spend: float) -> float:
    """ROMI, %: возврат на маркетинговые расходы."""
    if ad_spend <= 0:
        raise ValueError("Рекламный бюджет должен быть больше нуля")
    return round((ad_revenue - ad_spend) / ad_spend * 100, 2)


def breakeven_units(fixed_costs: float, price: float, variable_cost: float) -> int:
    """Точка безубыточности в штуках: сколько продать, чтобы выйти в ноль."""
    unit_margin = price - variable_cost
    if unit_margin <= 0:
        raise ValueError("Цена должна быть выше переменных затрат на единицу")
    if fixed_costs < 0:
        raise ValueError("Постоянные затраты не могут быть отрицательными")
    import math

    return math.ceil(fixed_costs / unit_margin)


@dataclass
class SalaryReport:
    gross: float  # начислено (оклад + процент + бонус)
    ndfl: float  # НДФЛ 13%
    net: float  # на руки


def salary(
    fixed: float,
    sales_volume: float = 0.0,
    percent: float = 0.0,
    bonus: float = 0.0,
    ndfl_rate: float = 13.0,
) -> SalaryReport:
    """Зарплата менеджера: оклад + процент с продаж + бонус, минус НДФЛ."""
    if min(fixed, sales_volume, percent, bonus) < 0 or ndfl_rate < 0 or ndfl_rate >= 100:
        raise ValueError("Некорректные входные значения")
    gross = fixed + sales_volume * percent / 100 + bonus
    ndfl = gross * ndfl_rate / 100
    return SalaryReport(round(gross, 2), round(ndfl, 2), round(gross - ndfl, 2))


@dataclass
class FunnelStage:
    name: str
    count: int
    conversion_from_prev_pct: float
    conversion_from_first_pct: float


def funnel(stages: list[tuple[str, int]]) -> list[FunnelStage]:
    """Воронка продаж: конверсия каждого шага от предыдущего и от первого."""
    if len(stages) < 2:
        raise ValueError("Нужно минимум два этапа воронки")
    first = stages[0][1]
    result: list[FunnelStage] = []
    prev = first
    for i, (name, count) in enumerate(stages):
        if count < 0:
            raise ValueError("Количество не может быть отрицательным")
        from_prev = 100.0 if i == 0 else (round(count / prev * 100, 2) if prev else 0.0)
        from_first = 100.0 if i == 0 else (round(count / first * 100, 2) if first else 0.0)
        result.append(FunnelStage(name, count, from_prev, from_first))
        prev = count
    return result


@dataclass
class UnitEconomics:
    """Юнит-экономика карточки товара на маркетплейсе."""

    price: float
    commission: float
    logistics: float
    cost: float
    ad_per_unit: float
    profit_per_unit: float
    margin_pct: float


def marketplace_unit(
    price: float,
    commission_pct: float,
    logistics: float,
    cost: float,
    ad_per_unit: float = 0.0,
) -> UnitEconomics:
    """Прибыль с одной продажи на маркетплейсе после комиссии, логистики и рекламы."""
    if price <= 0:
        raise ValueError("Цена должна быть больше нуля")
    if not 0 <= commission_pct < 100:
        raise ValueError("Комиссия должна быть от 0 до 100%")
    if min(logistics, cost, ad_per_unit) < 0:
        raise ValueError("Затраты не могут быть отрицательными")
    commission = price * commission_pct / 100
    profit = price - commission - logistics - cost - ad_per_unit
    margin = profit / price * 100
    return UnitEconomics(
        price,
        round(commission, 2),
        logistics,
        cost,
        ad_per_unit,
        round(profit, 2),
        round(margin, 2),
    )


@dataclass
class CardFunnel:
    """Воронка карточки маркетплейса — метрики для дизайнера и менеджера."""

    ctr_pct: float  # показы -> клики (CTR карточки)
    cart_pct: float  # клики -> корзина
    order_pct: float  # корзина -> заказ
    total_pct: float  # показы -> заказ
    drr_pct: float | None  # доля рекламных расходов от выручки


def card_funnel(
    impressions: int,
    clicks: int,
    carts: int,
    orders: int,
    ad_spend: float | None = None,
    revenue: float | None = None,
) -> CardFunnel:
    if min(impressions, clicks, carts, orders) < 0:
        raise ValueError("Значения не могут быть отрицательными")
    ctr = round(clicks / impressions * 100, 2) if impressions else 0.0
    cart = round(carts / clicks * 100, 2) if clicks else 0.0
    order = round(orders / carts * 100, 2) if carts else 0.0
    total = round(orders / impressions * 100, 2) if impressions else 0.0
    drr = None
    if ad_spend is not None and revenue:
        drr = round(ad_spend / revenue * 100, 2)
    return CardFunnel(ctr, cart, order, total, drr)
