import pandas as pd
import pytest

from wareon.services import qa


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Товар": ["Чехол", "Кабель", "Чехол", "Зарядка"],
            "Выручка": [1500.0, 700.0, 1600.0, 2500.0],
            "Количество": [3, 2, 3, 1],
        }
    )


class TestAggregates:
    def test_sum(self, df):
        assert "6,300" in qa.answer(df, "какая сумма выручки?")

    def test_mean(self, df):
        assert "1,575" in qa.answer(df, "средняя выручка")

    def test_count(self, df):
        assert "4 строк" in qa.answer(df, "сколько строк в таблице?")

    def test_max_plain_number(self, df):
        # «максимальная выручка» без группировки — просто максимум значения
        answer = qa.answer(df, "максимальная выручка")
        assert "2,500" in answer or "Зарядка" in answer

    def test_case_declension(self, df):
        # «по количеству» должно сматчиться со столбцом «Количество»
        assert "9" in qa.answer(df, "сумма по количеству")


class TestGrouping:
    def test_top(self, df):
        answer = qa.answer(df, "топ товаров по выручке")
        assert "Чехол" in answer
        assert answer.index("Чехол") < answer.index("Кабель")

    def test_best_seller(self, df):
        answer = qa.answer(df, "какой товар принёс больше всего выручки?")
        assert "Чехол" in answer  # 1500 + 1600 = 3100 > 2500

    def test_worst_seller(self, df):
        answer = qa.answer(df, "какой товар принёс меньше всего?")
        assert "Кабель" in answer


class TestFallback:
    def test_unknown_question(self, df):
        answer = qa.answer(df, "как дела?")
        assert "Столбцы таблицы" in answer

    def test_empty_table(self):
        assert "пуста" in qa.answer(pd.DataFrame(), "сумма")
