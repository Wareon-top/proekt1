from datetime import datetime

from wareon.handlers.crm import _parse_date, ingest_paid_leads


def test_parse_date_formats():
    assert _parse_date("2026-07-18") == datetime(2026, 7, 18)
    assert _parse_date("18.07.2026") == datetime(2026, 7, 18)
    assert _parse_date("") is None
    assert _parse_date(None) is None
    assert _parse_date("мусор") is None


def test_ingest_paid_leads_basic():
    now = datetime(2026, 7, 20)
    leads = [
        {"name": "Магазин А", "amount": 15000, "date": "2026-07-18"},
        {"name": "Магазин Б", "amount": 8000, "date": ""},
    ]
    sales = ingest_paid_leads(555, leads, now)
    assert len(sales) == 2
    assert sales[0].revenue == 15000 and sales[0].product == "Магазин А"
    assert sales[0].created_at == datetime(2026, 7, 18)
    assert sales[0].source == "CRM"
    assert sales[1].created_at == now  # без даты — текущий момент


def test_ingest_skips_zero_and_bad():
    now = datetime(2026, 7, 20)
    leads = [
        {"name": "Ноль", "amount": 0, "date": ""},
        {"name": "Мусор", "amount": "abc", "date": ""},
        {"name": "Ок", "amount": 5000, "date": ""},
    ]
    sales = ingest_paid_leads(555, leads, now)
    assert len(sales) == 1
    assert sales[0].revenue == 5000


def test_ingest_empty():
    assert ingest_paid_leads(1, [], datetime(2026, 7, 20)) == []
