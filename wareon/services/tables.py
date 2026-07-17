"""Умные таблицы: разбор загруженных CSV/XLSX и автоматическая сводка."""

import io

import pandas as pd

MAX_PREVIEW_ROWS = 5


def load_table(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    name = file_name.lower()
    buffer = io.BytesIO(file_bytes)
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(buffer)
    if name.endswith(".csv"):
        try:
            return pd.read_csv(buffer)
        except (pd.errors.ParserError, UnicodeDecodeError):
            buffer.seek(0)
            return pd.read_csv(buffer, sep=";", encoding="cp1251")
    raise ValueError("Поддерживаются только файлы .xlsx и .csv")


def summarize_table(df: pd.DataFrame, file_name: str) -> str:
    """Текстовая сводка по таблице: структура, числовые метрики, топ категорий."""
    if df.empty:
        return f"Файл «{file_name}» пуст — анализировать нечего."

    lines = [
        f"📊 Анализ таблицы «{file_name}»",
        f"Строк: {len(df)}, столбцов: {len(df.columns)}",
        "",
        "Столбцы: " + ", ".join(str(c) for c in df.columns[:15]),
    ]

    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        lines.append("")
        lines.append("🔢 Числовые столбцы:")
        for col in list(numeric.columns)[:8]:
            s = numeric[col].dropna()
            if s.empty:
                continue
            lines.append(
                f"• {col}: сумма {s.sum():,.2f}, среднее {s.mean():,.2f}, "
                f"мин {s.min():,.2f}, макс {s.max():,.2f}"
            )

    categorical = df.select_dtypes(exclude="number")
    for col in list(categorical.columns)[:3]:
        top = categorical[col].dropna().value_counts().head(3)
        if top.empty:
            continue
        top_str = ", ".join(f"{idx} ({cnt})" for idx, cnt in top.items())
        lines.append(f"🏷 Топ по «{col}»: {top_str}")

    empty_cells = int(df.isna().sum().sum())
    if empty_cells:
        lines.append(f"⚠️ Пустых ячеек: {empty_cells}")

    return "\n".join(lines)
