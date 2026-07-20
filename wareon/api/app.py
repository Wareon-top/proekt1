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
from wareon.services import agent, ai, reports
from wareon.services.metrics import build_panel


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Wareon Analytics API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
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


@app.get("/api/panel", response_model=schemas.PanelResponse)
async def panel(days: int = 7, uid: int = Depends(current_user)) -> schemas.PanelResponse:
    """Пульт метрик: движок метрик со всеми трендами и статусами (ИИ-первый экран)."""
    days = max(1, min(days, 365))
    async with session_factory() as session:
        p = await build_panel(session, uid, days=days)
    revenue = next((m for m in p.metrics if m.key == "revenue"), None)
    return schemas.PanelResponse(
        has_data=bool(revenue and revenue.value),
        days=p.days,
        forecast_revenue=p.forecast_revenue,
        revenue_series=p.revenue_series,
        growth_points=[m.title for m in p.growth_points],
        bottlenecks=[m.title for m in p.bottlenecks],
        metrics=[
            schemas.MetricOut(
                key=m.key,
                title=m.title,
                unit=m.unit,
                area=m.area,
                value=m.value,
                prev=m.prev,
                trend_pct=m.trend_pct,
                status=m.status,
                custom=m.custom,
            )
            for m in p.metrics
        ],
    )


@app.post("/api/chat", response_model=schemas.ChatResponse)
async def chat(req: schemas.ChatRequest, uid: int = Depends(current_user)) -> schemas.ChatResponse:
    """Живой чат с ИИ-оркестратором — тот же ассистент, что и в боте."""
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    if not settings.ai_enabled:
        return schemas.ChatResponse(enabled=False, text=ai.DISABLED_MSG)
    async with session_factory() as session:
        result = await agent.run_agent(session, uid, message)
    return schemas.ChatResponse(enabled=True, text=result.text, actions=result.actions)


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
