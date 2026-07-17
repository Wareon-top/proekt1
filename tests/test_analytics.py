import pytest

from wareon.services import analytics


class TestProfit:
    def test_basic(self):
        r = analytics.profit_report(100_000, 60_000)
        assert r.profit == 40_000
        assert r.margin_pct == 40.0
        assert r.markup_pct == pytest.approx(66.67)

    def test_zero_revenue(self):
        r = analytics.profit_report(0, 0)
        assert r.profit == 0
        assert r.margin_pct == 0.0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            analytics.profit_report(-1, 0)


class TestConversion:
    def test_basic(self):
        assert analytics.conversion(1000, 37) == 3.7

    def test_zero_visitors(self):
        assert analytics.conversion(0, 0) == 0.0

    def test_more_actions_than_visitors(self):
        with pytest.raises(ValueError):
            analytics.conversion(10, 11)


class TestAverageCheck:
    def test_basic(self):
        assert analytics.average_check(150_000, 42) == pytest.approx(3571.43)

    def test_zero_orders(self):
        assert analytics.average_check(1000, 0) == 0.0


class TestRoi:
    def test_positive(self):
        assert analytics.roi(50_000, 200_000) == 25.0

    def test_negative_profit(self):
        assert analytics.roi(-10_000, 100_000) == -10.0

    def test_zero_investment(self):
        with pytest.raises(ValueError):
            analytics.roi(100, 0)


class TestRomi:
    def test_basic(self):
        assert analytics.romi(300_000, 100_000) == 200.0

    def test_lossmaking(self):
        assert analytics.romi(50_000, 100_000) == -50.0


class TestBreakeven:
    def test_basic(self):
        assert analytics.breakeven_units(100_000, 1500, 900) == 167

    def test_rounds_up(self):
        assert analytics.breakeven_units(100, 30, 20) == 10

    def test_price_below_variable(self):
        with pytest.raises(ValueError):
            analytics.breakeven_units(1000, 100, 100)


class TestSalary:
    def test_full(self):
        r = analytics.salary(50_000, 800_000, 5, 10_000)
        assert r.gross == 100_000
        assert r.ndfl == 13_000
        assert r.net == 87_000

    def test_fixed_only(self):
        r = analytics.salary(50_000)
        assert r.gross == 50_000
        assert r.net == 43_500

    def test_bad_ndfl(self):
        with pytest.raises(ValueError):
            analytics.salary(50_000, ndfl_rate=100)


class TestFunnel:
    def test_basic(self):
        stages = analytics.funnel([("показы", 10_000), ("клики", 800), ("заказы", 56)])
        assert stages[0].conversion_from_prev_pct == 100.0
        assert stages[1].conversion_from_prev_pct == 8.0
        assert stages[2].conversion_from_prev_pct == 7.0
        assert stages[2].conversion_from_first_pct == 0.56

    def test_single_stage_raises(self):
        with pytest.raises(ValueError):
            analytics.funnel([("один", 10)])


class TestMarketplaceUnit:
    def test_profitable(self):
        u = analytics.marketplace_unit(1500, 20, 80, 600, 50)
        assert u.commission == 300.0
        assert u.profit_per_unit == 470.0
        assert u.margin_pct == pytest.approx(31.33)

    def test_lossmaking(self):
        u = analytics.marketplace_unit(500, 25, 100, 400)
        assert u.profit_per_unit < 0

    def test_bad_commission(self):
        with pytest.raises(ValueError):
            analytics.marketplace_unit(1000, 100, 0, 0)


class TestCardFunnel:
    def test_basic(self):
        f = analytics.card_funnel(50_000, 2500, 400, 120)
        assert f.ctr_pct == 5.0
        assert f.cart_pct == 16.0
        assert f.order_pct == 30.0
        assert f.total_pct == 0.24
        assert f.drr_pct is None

    def test_with_drr(self):
        f = analytics.card_funnel(50_000, 2500, 400, 120, ad_spend=30_000, revenue=180_000)
        assert f.drr_pct == pytest.approx(16.67)

    def test_zero_impressions(self):
        f = analytics.card_funnel(0, 0, 0, 0)
        assert f.ctr_pct == 0.0
