import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from wareon.api.app import app

    with TestClient(app) as c:  # startup создаёт таблицы
        yield c


async def _seed(uid: int) -> None:
    from wareon.db.base import session_factory
    from wareon.db.models import Sale

    async with session_factory() as s:
        s.add(Sale(user_tg_id=uid, revenue=1500, cost=900, product="Чехол", source="сайт"))
        s.add(Sale(user_tg_id=uid, revenue=1600, cost=1000, product="Чехол", source="сайт"))
        s.add(Sale(user_tg_id=uid, revenue=700, cost=1200, product="Зарядка", source="авито"))
        await s.commit()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_pulse_requires_auth(client):
    # без dev_user_id и без подписи — 401
    assert client.get("/api/pulse").status_code == 401


def test_pulse_returns_real_data(client):
    uid = 777001
    asyncio.run(_seed(uid))
    r = client.get("/api/pulse", params={"dev_user_id": uid, "days": 30})
    assert r.status_code == 200
    data = r.json()
    assert data["has_data"] is True
    assert data["orders"] == 3
    assert data["revenue"] == 3800.0
    # топ прибыльных: Чехол в плюсе (+1200), Зарядка в минусе (−500)
    assert data["top_products"][0]["name"] == "Чехол"
    assert data["top_products"][0]["profit"] == 1200.0
    assert data["antirating"][0]["name"] == "Зарядка"
    assert data["antirating"][0]["profit"] == -500.0


def test_pulse_empty_user(client):
    r = client.get("/api/pulse", params={"dev_user_id": 999999})
    assert r.status_code == 200
    assert r.json()["has_data"] is False
