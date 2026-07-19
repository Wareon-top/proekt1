import pytest

from wareon.handlers.pulse import _parse_args, format_panel
from wareon.services.metrics.panel import (
    STATUS_BOTTLENECK,
    STATUS_GROWTH,
    STATUS_NA,
    MetricValue,
    Panel,
)


class TestParseArgs:
    def test_default(self):
        assert _parse_args("") == (7, {})

    def test_days_only(self):
        assert _parse_args("30") == (30, {})

    def test_manual_values(self):
        days, manual = _parse_args("7 ad=3000 visitors=900")
        assert days == 7
        assert manual == {"ad": 3000.0, "visitors": 900.0}

    def test_comma_decimal(self):
        _, manual = _parse_args("ad=1500,5")
        assert manual["ad"] == 1500.5

    def test_rejects_zero_days(self):
        with pytest.raises(ValueError):
            _parse_args("0")

    def test_rejects_too_many_days(self):
        with pytest.raises(ValueError):
            _parse_args("400")


class TestFormatPanel:
    def _panel(self):
        return Panel(
            days=7,
            metrics=[
                MetricValue("revenue", "Выручка", "₽", "finance", 12000, 4800, 150.0, STATUS_GROWTH),
                MetricValue("cost", "Себестоимость", "₽", "finance", 4200, 3000, 40.0, STATUS_BOTTLENECK),
                MetricValue("drr_pct", "ДРР", "%", "marketing", None, None, None, STATUS_NA),
                MetricValue("mine", "Моя метрика", "%", "custom", 20.0, 10.0, 100.0, STATUS_GROWTH, custom=True),
            ],
            forecast_revenue=19200.0,
        )

    def test_contains_title_and_areas(self):
        text = format_panel(self._panel())
        assert "Пульт за 7 дн" in text
        assert "Финансы" in text
        assert "Маркетинг" in text

    def test_growth_and_bottleneck_sections(self):
        text = format_panel(self._panel())
        assert "Точки роста" in text and "Выручка" in text
        assert "Узкие места" in text and "Себестоимость" in text

    def test_na_shown(self):
        text = format_panel(self._panel())
        assert "нет данных" in text

    def test_custom_tag_and_forecast(self):
        text = format_panel(self._panel())
        assert "🤖" in text  # кастомная метрика помечена
        assert "Прогноз" in text and "19 200" in text
