from pydantic import BaseModel


class ProductProfit(BaseModel):
    name: str
    profit: float


class DayRevenue(BaseModel):
    day: str
    revenue: float


class SourceRevenue(BaseModel):
    name: str
    revenue: float


class BriefResponse(BaseModel):
    enabled: bool     # подключён ли ИИ (есть ключ)
    has_data: bool
    text: str


class MetricOut(BaseModel):
    key: str
    title: str
    unit: str
    area: str
    value: float | None
    prev: float | None = None
    trend_pct: float | None = None
    status: str            # growth | bottleneck | flat | na
    custom: bool = False


class PanelResponse(BaseModel):
    has_data: bool
    days: int
    forecast_revenue: float | None = None
    growth_points: list[str] = []
    bottlenecks: list[str] = []
    metrics: list[MetricOut] = []


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    enabled: bool          # подключён ли ИИ (есть ключ)
    text: str
    actions: list[str] = []


class PulseResponse(BaseModel):
    has_data: bool
    days: int
    net_today: float          # заработано чистыми с начала дня
    revenue: float
    cost: float
    profit: float
    margin_pct: float
    average_check: float
    orders: int
    revenue_delta_pct: float | None = None
    margin_delta_pp: float | None = None
    best_weekday: str | None = None
    top_products: list[ProductProfit] = []
    antirating: list[ProductProfit] = []
    by_day: list[DayRevenue] = []
    by_source: list[SourceRevenue] = []
