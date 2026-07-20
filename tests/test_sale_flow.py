import asyncio

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from wareon.handlers import sale


class Msg:
    def __init__(self, text=None, uid=1):
        self.text = text
        self.sent = []

        class U:
            id = uid

        self.from_user = U()

    async def answer(self, t, reply_markup=None):
        self.sent.append(t)


def _ctx():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def test_guided_sale_saves():
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import Sale

    async def flow():
        await init_db()
        ctx = _ctx()
        await ctx.set_state(sale.SaleFlow.revenue)
        m1 = Msg("15 000", uid=920001)
        await sale.step_revenue(m1, ctx)
        assert "шаг 2/3" in m1.sent[-1]
        m2 = Msg("8000", uid=920001)
        await sale.step_cost(m2, ctx)
        assert "шаг 3/3" in m2.sent[-1]
        m3 = Msg("сайт", uid=920001)
        await sale.step_source(m3, ctx)
        assert "Записал" in m3.sent[-1]
        assert await ctx.get_state() is None  # состояние очищено
        async with session_factory() as s:
            row = await s.scalar(select(Sale).where(Sale.user_tg_id == 920001))
        return row

    row = asyncio.run(flow())
    assert row is not None
    assert row.revenue == 15000.0
    assert row.cost == 8000.0
    assert row.source == "сайт"


def test_sale_rejects_bad_number():
    async def flow():
        ctx = _ctx()
        await ctx.set_state(sale.SaleFlow.revenue)
        m = Msg("абв", uid=920002)
        await sale.step_revenue(m, ctx)
        # остались на том же шаге, просит число
        assert "число" in m.sent[-1].lower()
        assert await ctx.get_state() == sale.SaleFlow.revenue.state

    asyncio.run(flow())
