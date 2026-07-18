"""Wareon API — «склад данных», отдающий дашборду реальные цифры пользователя.

Каждый запрос авторизуется подписью Telegram Web App, поэтому клиент видит
только свои данные. Данные лежат в той же БД, куда пишет бот.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from wareon.api import schemas
from wareon.api.auth import validate_init_data
from wareon.config import settings
from wareon.db.base import init_db, session_factory
from wareon.services import ai, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Wareon Analytics API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


async def current_user(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    init_data: str | None = Query(default=None),
    dev_user_id: int | None = Query(default=None),
) -> int:
    """Определяет пользователя по подписи Telegram. dev_user_id — только локально."""
    raw = x_init_data or init_data
    if raw:
        uid = validate_init_data(raw, settings.bot_token)
        if uid is not None:
            return uid
    # локальная разработка без бота: разрешаем явный id
    if dev_user_id is not None and not settings.bot_token:
        return dev_user_id
    raise HTTPException(status_code=401, detail="Некорректные данные авторизации Telegram")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/brief", response_model=schemas.BriefResponse)
async def brief(uid: int = Depends(current_user)) -> schemas.BriefResponse:
    async with session_factory() as session:
        s = await reports.sales_summary(session, uid, 7)
        text = await ai.daily_brief(session, uid)
    return schemas.BriefResponse(
        enabled=settings.ai_enabled, has_data=s.orders > 0, text=text
    )


@app.get("/api/pulse", response_model=schemas.PulseResponse)
async def pulse(days: int = 7, uid: int = Depends(current_user)) -> schemas.PulseResponse:
    days = max(1, min(days, 365))
    async with session_factory() as session:
        s = await reports.sales_summary(session, uid, days)
        net_today = await reports.today_profit(session, uid)

    products = sorted(s.by_product.items(), key=lambda kv: kv[1], reverse=True)
    top = [schemas.ProductProfit(name=n, profit=p) for n, p in products if p > 0][:5]
    anti = [
        schemas.ProductProfit(name=n, profit=p)
        for n, p in sorted(s.by_product.items(), key=lambda kv: kv[1])
        if p < 0
    ][:5]

    return schemas.PulseResponse(
        has_data=s.orders > 0,
        days=s.days,
        net_today=net_today,
        revenue=s.revenue,
        cost=s.cost,
        profit=s.profit,
        margin_pct=s.margin_pct,
        average_check=s.average_check,
        orders=s.orders,
        revenue_delta_pct=s.revenue_delta_pct,
        margin_delta_pp=s.margin_delta_pp,
        best_weekday=s.best_weekday,
        top_products=top,
        antirating=anti,
        by_day=[schemas.DayRevenue(day=d, revenue=r) for d, r in s.by_day.items()],
        by_source=[
            schemas.SourceRevenue(name=n, revenue=round(r, 2))
            for n, r in sorted(s.by_source.items(), key=lambda kv: -kv[1])
        ],
    )
