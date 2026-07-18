from datetime import datetime, timezone

import pandas as pd
import pytest

from wareon.services import ingest


def test_detect_columns_russian():
    df = pd.DataFrame({"Дата": [], "Товар": [], "Выручка": [], "Себестоимость": [], "Источник": []})
    m = ingest.detect_columns(df)
    assert m["date"] == "Дата"
    assert m["product"] == "Товар"
    assert m["revenue"] == "Выручка"
    assert m["cost"] == "Себестоимость"
    assert m["source"] == "Источник"


def test_detect_columns_english():
    df = pd.DataFrame({"date": [], "product": [], "revenue": [], "cost": []})
    m = ingest.detect_columns(df)
    assert m["revenue"] == "revenue"
    assert m["product"] == "product"


def test_detect_columns_no_revenue():
    df = pd.DataFrame({"foo": [], "bar": []})
    assert "revenue" not in ingest.detect_columns(df)


class TestToFloat:
    def test_spaces_and_currency(self):
        assert ingest._to_float("15 000 ₽") == 15000.0

    def test_comma_decimal(self):
        assert ingest._to_float("1 234,50") == 1234.5

    def test_plain_number(self):
        assert ingest._to_float(4200) == 4200.0

    def test_garbage(self):
        assert ingest._to_float("—") is None


def test_build_sales_basic():
    df = pd.DataFrame(
        {
            "Дата": ["01.07.2026", "02.07.2026"],
            "Товар": ["Чехол", "Кабель"],
            "Выручка": ["1 500", "700"],
            "Себестоимость": [900, 400],
        }
    )
    m = ingest.detect_columns(df)
    rows = ingest.build_sales(df, m, datetime.now(timezone.utc))
    assert len(rows) == 2
    assert rows[0]["revenue"] == 1500.0
    assert rows[0]["cost"] == 900.0
    assert rows[0]["product"] == "Чехол"
    assert rows[0]["created_at"].year == 2026


def test_build_sales_skips_rows_without_revenue():
    df = pd.DataFrame({"Выручка": ["1000", "нет", ""], "Товар": ["A", "B", "C"]})
    m = ingest.detect_columns(df)
    rows = ingest.build_sales(df, m, datetime.now(timezone.utc))
    assert len(rows) == 1


def test_build_sales_no_revenue_column():
    df = pd.DataFrame({"Товар": ["A"]})
    assert ingest.build_sales(df, {}, datetime.now(timezone.utc)) == []
