from wareon.services.reports import SalesSummary, delta_pct, format_summary, recommendation


def make_summary(**kwargs) -> SalesSummary:
    base = dict(
        days=7,
        orders=10,
        revenue=100_000.0,
        cost=60_000.0,
        profit=40_000.0,
        margin_pct=40.0,
        average_check=10_000.0,
        by_source={"сайт": 60_000.0, "авито": 40_000.0},
        by_day={"01.07": 50_000.0, "02.07": 50_000.0},
    )
    base.update(kwargs)
    return SalesSummary(**base)


class TestDeltaPct:
    def test_growth(self):
        assert delta_pct(120, 100) == 20.0

    def test_drop(self):
        assert delta_pct(80, 100) == -20.0

    def test_no_prev(self):
        assert delta_pct(100, 0) is None


class TestFormatSummary:
    def test_shows_deltas(self):
        text = format_summary(
            make_summary(revenue_delta_pct=23.5, prev_orders=8, prev_revenue=81_000.0)
        )
        assert "▲ +23.5%" in text
        assert "Прошлый период: 8 заказов" in text

    def test_no_deltas_without_prev(self):
        text = format_summary(make_summary())
        assert "Прошлый период" not in text

    def test_best_weekday(self):
        text = format_summary(make_summary(best_weekday="суббота"))
        assert "суббота" in text


class TestRecommendation:
    def test_empty(self):
        assert "/sale" in recommendation(make_summary(orders=0, revenue=0.0))

    def test_revenue_drop_beats_other_rules(self):
        r = recommendation(make_summary(revenue_delta_pct=-35.0))
        assert "упала" in r

    def test_low_margin(self):
        r = recommendation(make_summary(margin_pct=10.0))
        assert "Маржа ниже 15%" in r

    def test_margin_drop(self):
        r = recommendation(make_summary(margin_delta_pp=-7.0))
        assert "п.п." in r

    def test_source_concentration(self):
        r = recommendation(make_summary(by_source={"сайт": 90_000.0, "авито": 10_000.0}))
        assert "сайт" in r

    def test_growth_praise(self):
        r = recommendation(make_summary(revenue_delta_pct=45.0))
        assert "Рост" in r

    def test_healthy(self):
        r = recommendation(make_summary())
        assert "здоровые" in r
