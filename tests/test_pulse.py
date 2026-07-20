import pytest

from wareon.handlers.pulse import _parse_args, format_panel, pulse_caption
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
                MetricValue("drr_pct", "ДРР", "%", "marketing", 25.0, 40.0, -37.5, STATUS_GROWTH),
                MetricValue("cac", "CAC", "₽", "clients", None, None, None, STATUS_NA),
                MetricValue("mine", "Моя метрика", "%", "custom", 20.0, 10.0, 100.0, STATUS_GROWTH, custom=True),
            ],
            forecast_revenue=19200.0,
        )

    # ── Полный список метрик (format_panel) ─────────────────────────────────
    def test_full_contains_title_and_areas(self):
        text = format_panel(self._panel())
        assert "Пульт · 7 дн" in text
        assert "Финансы" in text
        assert "Маркетинг" in text

    def test_full_has_verdict(self):
        assert "Растёшь" in format_panel(self._panel())

    def test_full_na_hidden_with_hint(self):
        text = format_panel(self._panel())
        assert "нет данных" not in text
        assert "ждут данных" in text

    def test_full_custom_tag(self):
        assert "🤖" in format_panel(self._panel())

    # ── Сжатая подпись под графиком (pulse_caption) ─────────────────────────
    def test_caption_verdict_and_kpis(self):
        cap = pulse_caption(self._panel())
        assert "Растёшь" in cap
        assert "Выручка" in cap and "Прибыль" not in cap  # прибыли нет в фикстуре
        assert "12 000 ₽" in cap

    def test_caption_growth_bottleneck_forecast(self):
        cap = pulse_caption(self._panel())
        assert "Рост:" in cap and "Выручка" in cap
        assert "Узко:" in cap and "Себестоимость" in cap
        assert "Прогноз" in cap and "19 200" in cap
