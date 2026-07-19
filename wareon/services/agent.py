"""ИИ-оркестратор Wareon: агент, который видит пульт, думает и заводит метрики.

Головной ИИ работает как руководитель через безопасные инструменты (tool-use):
читает метрики, показывает точки роста и узкие места, сам заводит новые метрики из
кирпичиков-формул. Уровень автономии выбирает клиент (Раздел 2 конституции).

Реальные вызовы модели — платные, их делает клиент своим ключом. Здесь только
логика цикла; в тестах вызов модели подменяется моком."""

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wareon.config import settings
from wareon.db.models import AgentSetting, CustomMetric
from wareon.services import ai
from wareon.services.knowledge import BUSINESS_KNOWLEDGE
from wareon.services.metrics import build_panel
from wareon.services.metrics.formula import FormulaError, validate_expression
from wareon.services.metrics.panel import STATUS_BOTTLENECK, STATUS_GROWTH, Panel

logger = logging.getLogger(__name__)

AUTONOMY_LEVELS = {"autopilot", "semi", "manual"}
DEFAULT_AUTONOMY = "semi"
MAX_STEPS = 6

# Переменные, доступные формулам метрик (совпадают с движком метрик).
BASE_VARS = {"revenue", "cost", "profit", "orders", "days", "ad_spend", "visitors"}

ROLE = """\
Ты — Wareon, ИИ бизнес-ассистент и оркестратор. Не просто отвечаешь на вопросы, а
ведёшь: сам смотришь данные через инструменты, находишь точки роста и узкие места,
заводишь метрики и говоришь, что делать.

Правила:
- Прежде чем судить о бизнесе, посмотри пульт через get_panel. Опирайся только на
  реальные цифры клиента, не выдумывай.
- Если для ответа нужна метрика, которой нет в пульте, — заведи её через add_metric
  (безопасная формула из базовых переменных).
- Пиши коротко, по-деловому, на русском, на «ты». Без воды.
- Проблему подавай рецептом: Симптом → Причина → Действие.
"""

TOOLS = [
    {
        "name": "get_panel",
        "description": (
            "Показывает пульт метрик бизнеса за период: значения, тренд к прошлому "
            "периоду, точки роста и узкие места, прогноз выручки. Вызывай первым, "
            "чтобы увидеть реальные данные клиента."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Период в днях (по умолчанию 7)"}
            },
            "required": [],
        },
    },
    {
        "name": "list_metrics",
        "description": "Список кастомных метрик клиента (заведённых человеком или ИИ).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_metric",
        "description": (
            "Заводит новую кастомную метрику из формулы над базовыми переменными: "
            "revenue, cost, profit, orders, days, ad_spend, visitors. Разрешена только "
            "арифметика + - * / ( ) над этими переменными. Пример формулы: "
            "'ad_spend / revenue * 100'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Короткий машинный ключ, латиницей"},
                "title": {"type": "string", "description": "Понятное название метрики"},
                "formula": {"type": "string", "description": "Формула над базовыми переменными"},
                "unit": {"type": "string", "description": "₽, %, шт или пусто"},
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "neutral"],
                    "description": "up — хорошо когда растёт; down — хорошо когда падает",
                },
            },
            "required": ["key", "title", "formula", "direction"],
        },
    },
]


def system_prompt() -> str:
    return ROLE + "\n\n" + BUSINESS_KNOWLEDGE


@dataclass
class AgentResult:
    text: str
    actions: list[str] = field(default_factory=list)
    # Метрики, предложенные ИИ и ждущие подтверждения: (id, название).
    pending: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class _Ctx:
    session: AsyncSession
    uid: int
    level: str
    pending: list[tuple[int, str]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


async def get_autonomy(session: AsyncSession, user_tg_id: int) -> str:
    setting = await session.scalar(
        select(AgentSetting).where(AgentSetting.user_tg_id == user_tg_id)
    )
    return setting.level if setting else DEFAULT_AUTONOMY


async def set_autonomy(session: AsyncSession, user_tg_id: int, level: str) -> None:
    if level not in AUTONOMY_LEVELS:
        raise ValueError(f"Неизвестный уровень автономии: {level}")
    setting = await session.scalar(
        select(AgentSetting).where(AgentSetting.user_tg_id == user_tg_id)
    )
    if setting:
        setting.level = level
    else:
        session.add(AgentSetting(user_tg_id=user_tg_id, level=level))
    await session.commit()


def _slug(raw: str) -> str:
    s = re.sub(r"[^a-z0-9_]", "", raw.strip().lower().replace(" ", "_")).strip("_")
    return s[:48] or "metric"


def _panel_for_model(panel: Panel) -> str:
    lines = [f"Пульт за {panel.days} дн (сравнение с прошлым периодом):"]
    for m in panel.metrics:
        val = "нет данных" if m.value is None else f"{m.value:g}{m.unit}"
        trend = "" if m.trend_pct is None else f", тренд {m.trend_pct:+g}%"
        mark = {STATUS_GROWTH: " [точка роста]", STATUS_BOTTLENECK: " [узкое место]"}.get(
            m.status, ""
        )
        tag = " (кастомная)" if m.custom else ""
        lines.append(f"- {m.title}: {val}{trend}{mark}{tag}")
    if panel.forecast_revenue is not None:
        lines.append(
            f"Прогноз выручки на следующие {panel.days} дн: {panel.forecast_revenue:g}"
        )
    return "\n".join(lines)


async def _tool_get_panel(ctx: _Ctx, args: dict) -> str:
    days = int(args.get("days") or 7)
    days = max(1, min(days, 365))
    panel = await build_panel(ctx.session, ctx.uid, days=days)
    return _panel_for_model(panel)


async def _tool_list_metrics(ctx: _Ctx, args: dict) -> str:
    rows = (
        await ctx.session.scalars(
            select(CustomMetric).where(CustomMetric.user_tg_id == ctx.uid)
        )
    ).all()
    if not rows:
        return "Кастомных метрик пока нет."
    out = []
    for m in rows:
        state = " (ждёт подтверждения)" if m.pending else ""
        out.append(f"- {m.title} [{m.key}] = {m.expression} ({m.created_by}){state}")
    return "\n".join(out)


async def _tool_add_metric(ctx: _Ctx, args: dict) -> str:
    key = _slug(str(args.get("key", "")))
    title = str(args.get("title", "")).strip() or key
    expr = str(args.get("formula", "")).strip()
    unit = str(args.get("unit", "")).strip()
    direction = str(args.get("direction", "up")).strip()
    if direction not in ("up", "down", "neutral"):
        direction = "up"
    try:
        validate_expression(expr, allowed=BASE_VARS)
    except FormulaError as exc:
        return f"Формула отклонена ({exc}). Используй только базовые переменные и арифметику."

    pending = ctx.level != "autopilot"
    existing = await ctx.session.scalar(
        select(CustomMetric).where(
            CustomMetric.user_tg_id == ctx.uid, CustomMetric.key == key
        )
    )
    if existing:
        existing.title, existing.expression, existing.unit = title, expr, unit
        existing.direction, existing.created_by, existing.pending = direction, "ai", pending
        cm = existing
    else:
        cm = CustomMetric(
            user_tg_id=ctx.uid,
            key=key,
            title=title,
            expression=expr,
            unit=unit,
            direction=direction,
            created_by="ai",
            pending=pending,
        )
        ctx.session.add(cm)
    await ctx.session.commit()
    await ctx.session.refresh(cm)

    if pending:
        ctx.pending.append((cm.id, title))
        return f"Метрика «{title}» предложена и ждёт подтверждения пользователя."
    ctx.actions.append(f"завёл метрику «{title}»")
    return f"Метрика «{title}» заведена и уже считается в пульте."


_TOOLS = {
    "get_panel": _tool_get_panel,
    "list_metrics": _tool_list_metrics,
    "add_metric": _tool_add_metric,
}


async def _run_tool(ctx: _Ctx, name: str, args: dict) -> str:
    handler = _TOOLS.get(name)
    if handler is None:
        return f"Неизвестный инструмент: {name}"
    try:
        return await handler(ctx, args or {})
    except Exception:
        logger.exception("Инструмент %s упал", name)
        return "Инструмент дал сбой, попробуй иначе."


async def _create_message(messages: list[dict]):
    """Один вызов модели с инструментами. Подменяется моком в тестах."""
    from anthropic import AsyncAnthropic  # ленивый импорт

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return await client.messages.create(
        model=settings.ai_model,
        max_tokens=2000,
        system=[
            {"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}
        ],
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        tools=TOOLS,
        messages=messages,
    )


def _text_of(response) -> str:
    return "".join(
        getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
    ).strip()


async def run_agent(session: AsyncSession, user_tg_id: int, user_message: str) -> AgentResult:
    """Гоняет ИИ-оркестратор: думает, зовёт инструменты, отвечает."""
    if not settings.ai_enabled:
        return AgentResult(ai.DISABLED_MSG)
    level = await get_autonomy(session, user_tg_id)
    ctx = _Ctx(session=session, uid=user_tg_id, level=level)
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for _ in range(MAX_STEPS):
        try:
            response = await _create_message(messages)
        except Exception:
            logger.exception("Вызов модели упал для %s", user_tg_id)
            return AgentResult(ai.ERROR_MSG, actions=ctx.actions, pending=ctx.pending)

        if getattr(response, "stop_reason", None) != "tool_use":
            return AgentResult(_text_of(response), actions=ctx.actions, pending=ctx.pending)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            result = await _run_tool(ctx, block.name, block.input)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result}
            )
        messages.append({"role": "user", "content": tool_results})

    return AgentResult(
        "Не смог завершить за отведённые шаги — уточни задачу.",
        actions=ctx.actions,
        pending=ctx.pending,
    )
