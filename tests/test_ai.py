import asyncio

import pytest

from wareon.services import ai
from wareon.services.reports import SalesSummary


def make_summary(**kw) -> SalesSummary:
    base = dict(
        days=7, orders=5, revenue=100000.0, cost=60000.0, profit=40000.0,
        margin_pct=40.0, average_check=20000.0,
        by_source={"сайт": 80000.0, "авито": 20000.0},
        by_day={"01.07": 100000.0},
        by_product={"Чехол": 30000.0, "Зарядка": -5000.0},
        revenue_delta_pct=12.5, best_weekday="суббота",
    )
    base.update(kw)
    return SalesSummary(**base)


def test_panel_context_from_metrics():
    from wareon.services.metrics.panel import (
        STATUS_BOTTLENECK,
        STATUS_GROWTH,
        MetricValue,
        Panel,
    )

    panel = Panel(
        days=7,
        metrics=[
            MetricValue("revenue", "Выручка", "₽", "finance", 12000, 6000, 100.0, STATUS_GROWTH),
            MetricValue("cost", "Себестоимость", "₽", "finance", 4000, 3000, 33.0, STATUS_BOTTLENECK),
        ],
        forecast_revenue=15000.0,
    )
    ctx = ai._panel_context(panel)
    assert "Точки роста: Выручка" in ctx
    assert "Узкие места: Себестоимость" in ctx
    assert "Прогноз выручки" in ctx


def test_build_context_has_real_numbers():
    ctx = ai.build_context(make_summary(), net_today=12345.0)
    assert "12 345" in ctx          # заработано сегодня
    assert "маржа: 40.0%" in ctx
    assert "Чехол" in ctx
    assert "+12.5%" in ctx
    assert "суббота" in ctx


async def _seed(uid: int) -> None:
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import Sale

    await init_db()
    async with session_factory() as s:
        s.add(Sale(user_tg_id=uid, revenue=1500, cost=900, product="Чехол"))
        await s.commit()


async def _run(uid: int, fn):
    from wareon.db.base import session_factory

    async with session_factory() as s:
        return await fn(s, uid)


def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(ai.settings, "anthropic_api_key", "", raising=False)
    asyncio.run(_seed(910001))
    out = asyncio.run(_run(910001, ai.daily_brief))
    assert out == ai.DISABLED_MSG


def test_no_data_message(monkeypatch):
    monkeypatch.setattr(ai.settings, "anthropic_api_key", "test-key", raising=False)
    asyncio.run(_seed(910099))  # создаёт таблицы + продажу другому пользователю

    async def flow():
        from wareon.db.base import session_factory

        async with session_factory() as s:
            return await ai.daily_brief(s, 910002)  # у этого пользователя продаж нет

    assert asyncio.run(flow()) == ai.NO_DATA_MSG


def test_brief_generates_and_caches(monkeypatch):
    monkeypatch.setattr(ai.settings, "anthropic_api_key", "test-key", raising=False)
    calls = {"n": 0}

    async def fake_call(system, user, max_tokens=1200):
        calls["n"] += 1
        assert "Данные бизнеса клиента" in user
        return "СВОДКА: всё ок"

    monkeypatch.setattr(ai, "_call_claude", fake_call)

    uid = 910003
    asyncio.run(_seed(uid))
    first = asyncio.run(_run(uid, ai.daily_brief))
    second = asyncio.run(_run(uid, ai.daily_brief))
    assert first == "СВОДКА: всё ок"
    assert second == first
    assert calls["n"] == 1  # второй раз — из кэша, без обращения к Клоду


def test_ask_uses_claude(monkeypatch):
    monkeypatch.setattr(ai.settings, "anthropic_api_key", "test-key", raising=False)

    async def fake_call(system, user, max_tokens=1200):
        assert "Вопрос клиента: почему упала прибыль" in user
        return "Потому что выросла себестоимость."

    monkeypatch.setattr(ai, "_call_claude", fake_call)

    uid = 910004
    asyncio.run(_seed(uid))

    async def flow():
        from wareon.db.base import session_factory

        async with session_factory() as s:
            return await ai.ask(s, uid, "почему упала прибыль")

    assert "себестоимость" in asyncio.run(flow())
