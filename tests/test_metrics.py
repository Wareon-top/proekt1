import asyncio
from datetime import datetime, timedelta

import pytest

from wareon.services.metrics import catalog
from wareon.services.metrics.formula import (
    FormulaError,
    evaluate,
    validate_expression,
    variables_in,
)
from wareon.services.metrics.panel import (
    STATUS_BOTTLENECK,
    STATUS_GROWTH,
    STATUS_NA,
    base_variables,
    build_panel,
    linear_forecast,
)


# ── Движок формул ────────────────────────────────────────────────────────────
class TestFormulaSafety:
    def test_basic_arithmetic(self):
        assert evaluate("a + b * 2", {"a": 1, "b": 3}) == 7

    def test_division_and_parens(self):
        assert evaluate("(a - b) / a * 100", {"a": 200, "b": 50}) == 75.0

    def test_div_by_zero_is_unavailable(self):
        assert evaluate("a / b", {"a": 10, "b": 0}) is None

    def test_missing_variable_is_unavailable(self):
        assert evaluate("ad_spend / revenue", {"revenue": 100}) is None

    def test_rejects_function_calls(self):
        with pytest.raises(FormulaError):
            validate_expression("__import__('os')")

    def test_rejects_attribute_access(self):
        with pytest.raises(FormulaError):
            validate_expression("a.__class__")

    def test_rejects_names_not_in_allowed(self):
        with pytest.raises(FormulaError):
            validate_expression("revenue / secret", allowed={"revenue", "cost"})

    def test_accepts_allowed_names(self):
        validate_expression("revenue - cost", allowed={"revenue", "cost"})

    def test_rejects_empty(self):
        with pytest.raises(FormulaError):
            validate_expression("")

    def test_variables_in(self):
        assert variables_in("revenue / cost * days") == {"revenue", "cost", "days"}


# ── Каталог ──────────────────────────────────────────────────────────────────
class TestCatalog:
    def test_keys_unique(self):
        keys = [m.key for m in catalog.BUILTIN_METRICS]
        assert len(keys) == len(set(keys))

    def test_all_expressions_valid(self):
        allowed = {"revenue", "cost", "profit", "orders", "days", "ad_spend", "visitors"}
        for m in catalog.BUILTIN_METRICS:
            validate_expression(m.expr, allowed=allowed)

    def test_by_area_groups(self):
        grouped = catalog.by_area()
        assert catalog.AREA_FINANCE in grouped
        assert any(m.key == "margin_pct" for m in grouped[catalog.AREA_FINANCE])


# ── Прогноз ──────────────────────────────────────────────────────────────────
class TestForecast:
    def test_flat_series(self):
        assert linear_forecast([100, 100, 100, 100], 4) == 400.0

    def test_rising_series(self):
        # 10,20,30,40 → тренд +10/день → следующие 2 дня ≈ 50+60 = 110
        assert linear_forecast([10, 20, 30, 40], 2) == 110.0

    def test_too_short(self):
        assert linear_forecast([100], 3) is None

    def test_never_negative(self):
        assert linear_forecast([100, 50, 10, 0], 5) >= 0


# ── Пульт на реальной БД ─────────────────────────────────────────────────────
def test_base_variables_single_query():
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import Sale

    async def flow():
        await init_db()
        uid = 700001
        async with session_factory() as s:
            s.add_all(
                [
                    Sale(user_tg_id=uid, revenue=1000, cost=400, created_at=datetime(2026, 7, 10)),
                    Sale(user_tg_id=uid, revenue=500, cost=100, created_at=datetime(2026, 7, 11)),
                ]
            )
            await s.commit()
            v = await base_variables(
                s, uid, datetime(2026, 7, 1), datetime(2026, 8, 1)
            )
        return v

    v = asyncio.run(flow())
    assert v["revenue"] == 1500
    assert v["cost"] == 500
    assert v["profit"] == 1000
    assert v["orders"] == 2


def test_build_panel_trend_and_status():
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import Sale

    async def flow():
        await init_db()
        uid = 700002
        now = datetime(2026, 7, 20)
        async with session_factory() as s:
            # прошлый период (7 дн назад): выручка 100
            s.add(Sale(user_tg_id=uid, revenue=100, cost=50, created_at=datetime(2026, 7, 8)))
            # текущий период: выручка 1000 — резкий рост
            s.add(Sale(user_tg_id=uid, revenue=1000, cost=200, created_at=datetime(2026, 7, 18)))
            await s.commit()
            panel = await build_panel(s, uid, days=7, now=now)
        return panel

    panel = asyncio.run(flow())
    rev = next(m for m in panel.metrics if m.key == "revenue")
    assert rev.value == 1000
    assert rev.prev == 100
    assert rev.status == STATUS_GROWTH
    assert panel.growth_points  # есть хотя бы одна точка роста


def test_build_panel_missing_data_is_na():
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import Sale

    async def flow():
        await init_db()
        uid = 700003
        async with session_factory() as s:
            s.add(Sale(user_tg_id=uid, revenue=500, cost=100, created_at=datetime(2026, 7, 18)))
            await s.commit()
            # без manual — ДРР (нужен ad_spend) не посчитается
            panel = await build_panel(s, uid, days=7, now=datetime(2026, 7, 20))
        return panel

    panel = asyncio.run(flow())
    drr = next(m for m in panel.metrics if m.key == "drr_pct")
    assert drr.value is None
    assert drr.status == STATUS_NA


def test_build_panel_with_manual_and_custom():
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import CustomMetric, Sale

    async def flow():
        await init_db()
        uid = 700004
        async with session_factory() as s:
            s.add(Sale(user_tg_id=uid, revenue=1000, cost=300, created_at=datetime(2026, 7, 18)))
            s.add(
                CustomMetric(
                    user_tg_id=uid,
                    key="marketing_pct",
                    title="Маркетинг %",
                    expression="ad_spend / revenue * 100",
                    unit="%",
                    direction="down",
                    created_by="ai",
                )
            )
            await s.commit()
            panel = await build_panel(
                s, uid, days=7, now=datetime(2026, 7, 20), manual={"ad_spend": 200}
            )
        return panel

    panel = asyncio.run(flow())
    drr = next(m for m in panel.metrics if m.key == "drr_pct")
    assert drr.value == 20.0  # 200 / 1000 * 100
    custom = next(m for m in panel.metrics if m.key == "marketing_pct")
    assert custom.custom is True
    assert custom.value == 20.0
