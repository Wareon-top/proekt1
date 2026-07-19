import pytest

from wareon.handlers import calc


def compute(key, values):
    return calc.CALCULATORS[key].compute(values)


def test_menu_lists_all_calculators():
    datas = [
        b.callback_data
        for row in calc.calc_menu_kb().inline_keyboard
        for b in row
        if b.callback_data
    ]
    for key in calc.CALCULATORS:
        assert f"calc:go:{key}" in datas


def test_profit():
    out = compute("profit", {"revenue": 100000, "cost": 60000})
    assert "40 000" in out  # прибыль
    assert "40.0%" in out   # маржа


def test_conversion():
    assert "3.7%" in compute("conversion", {"visitors": 1000, "actions": 37})


def test_conversion_invalid_raises():
    with pytest.raises(ValueError):
        compute("conversion", {"visitors": 100, "actions": 200})


def test_avg_check():
    assert "3 571" in compute("avg", {"revenue": 150000, "orders": 42})


def test_roi_romi():
    assert "25.0%" in compute("roi", {"profit": 50000, "investment": 200000})
    assert "200.0%" in compute("romi", {"ad_revenue": 300000, "ad_spend": 100000})


def test_breakeven():
    assert "167 шт" in compute(
        "breakeven", {"fixed": 100000, "price": 1500, "variable": 900}
    )


def test_salary():
    out = compute("salary", {"fixed": 50000, "volume": 800000, "percent": 5, "bonus": 10000})
    assert "87 000" in out  # на руки


def test_unit():
    out = compute(
        "unit", {"price": 1500, "commission": 20, "logistics": 80, "cost": 600, "ad": 50}
    )
    assert "470" in out          # прибыль с продажи
    assert "31.33%" in out       # маржа


def test_card_funnel():
    out = compute(
        "card", {"impressions": 50000, "clicks": 2500, "carts": 400, "orders": 120}
    )
    assert "5.0%" in out   # CTR
    assert "0.24%" in out  # показы→заказ


def test_prompt_shows_step():
    p = calc._prompt(calc.CALCULATORS["profit"], 0)
    assert "шаг 1/2" in p
    assert "Выручка" in p
