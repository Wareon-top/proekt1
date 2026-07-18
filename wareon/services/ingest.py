"""Приёмка данных: распознаёт колонки загруженной таблицы и раскладывает
строки в продажи (Sale) конкретного пользователя.

Работает по эвристике названий колонок (рус/англ), поэтому клиенту не нужно
приводить файл к строгому формату.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.db.models import Sale

# ключевые слова для сопоставления колонок (в нижнем регистре, по вхождению)
_KEYWORDS: dict[str, list[str]] = {
    "revenue": ["выручка", "revenue", "оборот", "сумма", "продаж", "amount", "итого", "доход"],
    "cost": ["себестоимость", "закупка", "закуп", "cost", "расход", "затрат"],
    "product": ["товар", "product", "наименование", "название", "позиция", "sku", "артикул", "item"],
    "source": ["источник", "канал", "source", "channel", "площадка"],
    "date": ["дата", "date", "день", "created", "time", "время"],
}


@dataclass
class IngestResult:
    inserted: int
    mapping: dict[str, str] = field(default_factory=dict)  # роль -> имя колонки
    skipped: int = 0
    error: str | None = None


def detect_columns(df: pd.DataFrame) -> dict[str, str]:
    """Сопоставляет роли (revenue/cost/product/source/date) с именами колонок."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for role, keys in _KEYWORDS.items():
        for col in df.columns:
            name = str(col).strip().lower()
            if col in used:
                continue
            if any(k in name for k in keys):
                mapping[role] = col
                used.add(col)
                break
    return mapping


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("\xa0", "").replace(" ", "").replace("₽", "").replace(",", ".")
    s = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def build_sales(df: pd.DataFrame, mapping: dict[str, str], now: datetime) -> list[dict]:
    """Готовит список продаж из таблицы. Строки без выручки пропускаются."""
    if "revenue" not in mapping:
        return []
    dates = None
    if "date" in mapping:
        dates = pd.to_datetime(df[mapping["date"]], errors="coerce", dayfirst=True)

    rows: list[dict] = []
    for i, (_, row) in enumerate(df.iterrows()):
        revenue = _to_float(row[mapping["revenue"]])
        if revenue is None or revenue < 0:
            continue
        cost = _to_float(row[mapping["cost"]]) if "cost" in mapping else 0.0
        created = now
        if dates is not None and not pd.isna(dates.iloc[i]):
            dt = dates.iloc[i].to_pydatetime()
            created = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        rows.append(
            {
                "revenue": round(revenue, 2),
                "cost": round(cost or 0.0, 2),
                "product": (str(row[mapping["product"]])[:128] if "product" in mapping else None),
                "source": (str(row[mapping["source"]])[:64] if "source" in mapping else None),
                "created_at": created,
            }
        )
    return rows


async def ingest_dataframe(
    session: AsyncSession, user_tg_id: int, df: pd.DataFrame
) -> IngestResult:
    """Распознаёт таблицу и сохраняет продажи пользователя в БД."""
    if df.empty:
        return IngestResult(inserted=0, error="Таблица пустая.")
    mapping = detect_columns(df)
    if "revenue" not in mapping:
        return IngestResult(
            inserted=0,
            mapping=mapping,
            error="Не нашёл колонку с выручкой. Назовите её «Выручка» / «Сумма» / «Revenue».",
        )
    now = datetime.now(timezone.utc)
    parsed = build_sales(df, mapping, now)
    for item in parsed:
        session.add(Sale(user_tg_id=user_tg_id, **item))
    await session.commit()
    return IngestResult(inserted=len(parsed), mapping=mapping, skipped=len(df) - len(parsed))
