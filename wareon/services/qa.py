"""Вопросы к таблице обычным текстом: «какой товар самый прибыльный?»,
«сумма выручки», «топ по количеству» — разбор без внешних API.
"""

import difflib
import re

import pandas as pd

TOP_N = 5

_AGG_PATTERNS: list[tuple[str, list[str]]] = [
    ("count", ["сколько строк", "количество строк", "число строк", "число записей"]),
    ("top", ["топ", "лучш", "самый прибыльн", "самые прода", "рейтинг"]),
    ("max", ["максим", "наибольш", "самый больш", "больше всего", "самая больш"]),
    ("min", ["миним", "наименьш", "меньше всего", "самый маленьк"]),
    ("mean", ["средн"]),
    ("sum", ["сумм", "итого", "всего", "общая", "общий"]),
]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zа-яё0-9_]+", text.lower())


def _similarity(token: str, column: str) -> float:
    if token == column:
        return 1.0
    if len(token) >= 4 and (token in column or column in token):
        return 0.9
    return difflib.SequenceMatcher(None, token, column).ratio()


def _match_column(tokens: list[str], columns: list[str]) -> str | None:
    """Лучшее соответствие слова из вопроса названию столбца (с учётом падежей)."""
    best: tuple[float, str | None] = (0.0, None)
    for col in columns:
        col_l = str(col).lower()
        for token in tokens:
            score = _similarity(token, col_l)
            if score > best[0]:
                best = (score, col)
    return best[1] if best[0] >= 0.72 else None


def _detect_agg(question_l: str) -> str | None:
    for agg, patterns in _AGG_PATTERNS:
        if any(p in question_l for p in patterns):
            return agg
    return None


def _fmt(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def answer(df: pd.DataFrame, question: str, file_name: str = "таблица") -> str:
    """Ответ на вопрос по таблице. Всегда возвращает текст (или подсказку)."""
    if df.empty:
        return "Таблица пуста — спросить не о чем."

    question_l = question.lower()
    tokens = _tokens(question)
    numeric_cols = [str(c) for c in df.select_dtypes(include="number").columns]
    other_cols = [str(c) for c in df.columns if str(c) not in numeric_cols]

    agg = _detect_agg(question_l)
    if agg == "count":
        return f"В таблице «{file_name}» {len(df)} строк."

    value_col = _match_column(tokens, numeric_cols)
    group_col = _match_column(tokens, other_cols)

    # «по <слово>» — уточнение столбца: числовой → метрика, текстовый → группировка
    po_match = re.search(r"\bпо\s+([a-zа-яё0-9_]+)", question_l)
    if po_match:
        col = _match_column([po_match.group(1)], numeric_cols + other_cols)
        if col in numeric_cols:
            value_col = col
        elif col:
            group_col = col

    if agg is None and value_col is None:
        return _hint(df, file_name)

    if value_col is None and numeric_cols:
        value_col = numeric_cols[0]
    if value_col is None:
        return _hint(df, file_name)
    if agg is None:
        agg = "sum"

    series = pd.to_numeric(df[value_col], errors="coerce").dropna()

    grouped_query = agg == "top" or (agg in ("max", "min") and group_col is not None)
    if grouped_query and (group_col or other_cols):
        gcol = group_col or other_cols[0]
        grouped = (
            df.assign(_v=pd.to_numeric(df[value_col], errors="coerce"))
            .groupby(gcol)["_v"]
            .sum()
            .dropna()
            .sort_values(ascending=(agg == "min"))
        )
        if grouped.empty:
            return _hint(df, file_name)
        if agg in ("max", "min"):
            name, val = grouped.index[0], grouped.iloc[0]
            word = "меньше" if agg == "min" else "больше"
            return f"{word.capitalize()} всего по «{value_col}»: {name} — {_fmt(val)}."
        lines = [f"🏆 Топ по «{value_col}» (группировка «{gcol}»):"]
        for i, (name, val) in enumerate(grouped.head(TOP_N).items(), 1):
            lines.append(f"{i}. {name} — {_fmt(val)}")
        return "\n".join(lines)

    if series.empty:
        return _hint(df, file_name)

    if agg == "mean":
        return f"Среднее по «{value_col}»: {_fmt(float(series.mean()))}."
    if agg == "max":
        return f"Максимум по «{value_col}»: {_fmt(float(series.max()))}."
    if agg == "min":
        return f"Минимум по «{value_col}»: {_fmt(float(series.min()))}."
    return f"Сумма по «{value_col}»: {_fmt(float(series.sum()))}."


def _hint(df: pd.DataFrame, file_name: str) -> str:
    cols = ", ".join(str(c) for c in df.columns[:10])
    return (
        f"Не понял вопрос к «{file_name}». Попробуйте так:\n"
        "• «сумма выручки»\n"
        "• «средний чек» / «среднее по количеству»\n"
        "• «топ товаров по выручке»\n"
        "• «какой товар принёс больше всего?»\n"
        "• «сколько строк»\n\n"
        f"Столбцы таблицы: {cols}"
    )
