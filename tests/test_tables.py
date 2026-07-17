import io

import pandas as pd
import pytest

from wareon.services import tables


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Товар": ["Чехол", "Кабель", "Чехол", "Зарядка"],
            "Выручка": [1500.0, 700.0, 1600.0, 2500.0],
            "Количество": [3, 2, 3, 1],
        }
    )


def test_load_csv(sample_df):
    df = tables.load_table(_csv_bytes(sample_df), "sales.csv")
    assert len(df) == 4
    assert "Выручка" in df.columns


def test_load_xlsx(sample_df):
    df = tables.load_table(_xlsx_bytes(sample_df), "sales.xlsx")
    assert len(df) == 4


def test_load_unsupported():
    with pytest.raises(ValueError):
        tables.load_table(b"hello", "notes.txt")


def test_summary_contains_metrics(sample_df):
    text = tables.summarize_table(sample_df, "sales.csv")
    assert "Строк: 4" in text
    assert "Выручка" in text
    assert "6,300.00" in text  # сумма выручки
    assert "Чехол" in text  # топ-категория


def test_summary_empty():
    text = tables.summarize_table(pd.DataFrame(), "empty.csv")
    assert "пуст" in text


def test_summary_reports_missing_cells(sample_df):
    sample_df.loc[0, "Выручка"] = None
    text = tables.summarize_table(sample_df, "sales.csv")
    assert "Пустых ячеек: 1" in text
