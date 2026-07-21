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

from datetime import datetime, timezone

from wareon.config import settings
from wareon.db.models import (
    AgentMemory,
    AgentSetting,
    AlertSetting,
    BrandVoice,
    CustomMetric,
    OutgoingPost,
    Reminder,
    ReportSubscription,
    TableUpload,
    TrackedChat,
)
from wareon.services import ai, reports
from wareon.services.knowledge import BUSINESS_KNOWLEDGE
from wareon.services.metrics import build_panel
from wareon.services.metrics.formula import FormulaError, validate_expression
from wareon.services.metrics.panel import STATUS_BOTTLENECK, STATUS_GROWTH, Panel
from wareon.services.scheduler import next_run

logger = logging.getLogger(__name__)

AUTONOMY_LEVELS = {"autopilot", "semi", "manual"}
DEFAULT_AUTONOMY = "semi"
MAX_STEPS = 8

# Переменные, доступные формулам метрик (совпадают с движком метрик).
BASE_VARS = {"revenue", "cost", "profit", "orders", "days", "ad_spend", "visitors"}

ROLE = """\
Ты — Wareon, ИИ бизнес-ассистент и оркестратор. Не просто отвечаешь на вопросы, а
ведёшь: сам смотришь данные через инструменты, находишь точки роста и узкие места,
заводишь метрики и говоришь, что делать.

Ты не только советуешь — ты действуешь: заводишь метрики, ставишь алерты и
напоминания, подписываешь на отчёты, запоминаешь важное о бизнесе.

Правила:
- Прежде чем судить о бизнесе, посмотри пульт через get_panel. Опирайся только на
  реальные цифры клиента, не выдумывай.
- Если для ответа нужна метрика, которой нет, — заведи её через add_metric.
- Узнал важный факт о бизнесе (ниша, товары, предпочтения) — сохрани через remember.
- Просят напомнить/следить/присылать отчёт — используй set_reminder, set_alert,
  schedule_report, а не обещай на словах.
- Клиент описал, как писать от его имени, — сохрани через set_voice и дальше пиши
  посты и сообщения в этом тоне.
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
    {
        "name": "get_report",
        "description": (
            "Детальная сводка по продажам за период: выручка, прибыль, маржа, средний "
            "чек, топ товаров, разрез по источникам. Для развёрнутого отчёта."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer"}},
            "required": [],
        },
    },
    {
        "name": "get_table",
        "description": (
            "Читает последнюю загруженную клиентом таблицу (её разбор: колонки, суммы). "
            "Используй, если вопрос про загруженный файл или таблицу."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "remember",
        "description": (
            "Сохраняет важный факт о бизнесе клиента в долговременную память "
            "(ниша, товары, предпочтения, договорённости) — пригодится в будущих разговорах."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
    },
    {
        "name": "set_alert",
        "description": (
            "Ставит алерт по марже: бот предупредит, если маржа за сутки упадёт ниже "
            "порога (в процентах)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"threshold_pct": {"type": "number"}},
            "required": ["threshold_pct"],
        },
    },
    {
        "name": "schedule_report",
        "description": (
            "Подписывает клиента на регулярный отчёт. kind: daily — ежедневный, "
            "weekly — еженедельный (по понедельникам), ai — утренняя ИИ-сводка. Время МСК."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["daily", "weekly", "ai"]},
                "hour": {"type": "integer"},
                "minute": {"type": "integer"},
            },
            "required": ["kind", "hour"],
        },
    },
    {
        "name": "set_reminder",
        "description": (
            "Ставит разовое напоминание: бот напишет клиенту текст в ближайшее "
            "наступление указанного времени (МСК)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "hour": {"type": "integer"},
                "minute": {"type": "integer"},
            },
            "required": ["text", "hour"],
        },
    },
    {
        "name": "list_channels",
        "description": "Список подключённых каналов/групп клиента, куда можно выложить пост.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_voice",
        "description": (
            "Сохраняет голос бренда — как клиент хочет, чтобы звучали посты и "
            "сообщения от его имени (тон, обращение, эмодзи, длина). Вызывай, когда "
            "клиент описал свой стиль. Дальше пиши посты именно в этом тоне."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Описание тона: например «дружелюбно, на ты, с эмодзи, коротко»",
                }
            },
            "required": ["description"],
        },
    },
    {
        "name": "post_to_channel",
        "description": (
            "Готовит пост в подключённый канал/группу. channel — название или часть "
            "названия чата из list_channels. На автопилоте публикует сразу, иначе — "
            "предлагает и ждёт подтверждения клиента. Пиши пост в стиле клиента."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Название канала/группы"},
                "text": {"type": "string", "description": "Текст поста"},
            },
            "required": ["channel", "text"],
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
    # Посты, ждущие подтверждения: (id, канал, превью текста).
    pending_posts: list[tuple[int, str, str]] = field(default_factory=list)


@dataclass
class _Ctx:
    session: AsyncSession
    uid: int
    level: str
    pending: list[tuple[int, str]] = field(default_factory=list)
    pending_posts: list[tuple[int, str, str]] = field(default_factory=list)
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


async def get_voice(session: AsyncSession, user_tg_id: int) -> str | None:
    voice = await session.scalar(
        select(BrandVoice).where(BrandVoice.user_tg_id == user_tg_id)
    )
    return voice.description if voice else None


async def set_voice(session: AsyncSession, user_tg_id: int, description: str) -> None:
    description = description.strip()[:500]
    voice = await session.scalar(
        select(BrandVoice).where(BrandVoice.user_tg_id == user_tg_id)
    )
    if voice:
        voice.description = description
    else:
        session.add(BrandVoice(user_tg_id=user_tg_id, description=description))
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


async def _tool_get_report(ctx: _Ctx, args: dict) -> str:
    days = max(1, min(int(args.get("days") or 7), 365))
    summary = await reports.sales_summary(ctx.session, ctx.uid, days)
    if summary.orders == 0:
        return "Продаж за период нет."
    return reports.format_summary(summary)


async def _tool_get_table(ctx: _Ctx, args: dict) -> str:
    row = await ctx.session.scalar(
        select(TableUpload)
        .where(TableUpload.user_tg_id == ctx.uid)
        .order_by(TableUpload.created_at.desc())
    )
    if row is None:
        return "Клиент не загружал таблиц."
    return f"Последняя таблица «{row.file_name}»:\n{row.summary}"


async def _tool_remember(ctx: _Ctx, args: dict) -> str:
    fact = str(args.get("fact", "")).strip()
    if not fact:
        return "Пустой факт — нечего запоминать."
    ctx.session.add(AgentMemory(user_tg_id=ctx.uid, content=fact[:500]))
    await ctx.session.commit()
    ctx.actions.append("запомнил факт о бизнесе")
    return "Запомнил."


async def _tool_set_alert(ctx: _Ctx, args: dict) -> str:
    try:
        threshold = float(args.get("threshold_pct"))
    except (TypeError, ValueError):
        return "Порог должен быть числом процентов."
    if not 0 < threshold < 100:
        return "Порог — от 0 до 100%."
    existing = await ctx.session.scalar(
        select(AlertSetting).where(AlertSetting.user_tg_id == ctx.uid)
    )
    if existing:
        existing.margin_threshold_pct = threshold
    else:
        ctx.session.add(AlertSetting(user_tg_id=ctx.uid, margin_threshold_pct=threshold))
    await ctx.session.commit()
    ctx.actions.append(f"поставил алерт по марже < {threshold:g}%")
    return f"Алерт поставлен: предупрежу, если маржа за сутки упадёт ниже {threshold:g}%."


async def _tool_schedule_report(ctx: _Ctx, args: dict) -> str:
    kind = str(args.get("kind", "")).strip()
    if kind not in ("daily", "weekly", "ai"):
        return "kind должен быть daily, weekly или ai."
    hour = int(args.get("hour") or 9)
    minute = int(args.get("minute") or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return "Некорректное время."
    now = datetime.now(timezone.utc)
    run_at = next_run(kind, hour, minute, now).replace(tzinfo=None)
    existing = await ctx.session.scalar(
        select(ReportSubscription).where(
            ReportSubscription.user_tg_id == ctx.uid, ReportSubscription.kind == kind
        )
    )
    if existing:
        existing.hour, existing.minute, existing.next_run_at = hour, minute, run_at
    else:
        ctx.session.add(
            ReportSubscription(
                user_tg_id=ctx.uid, kind=kind, hour=hour, minute=minute, next_run_at=run_at
            )
        )
    await ctx.session.commit()
    names = {"daily": "ежедневный отчёт", "weekly": "недельный отчёт", "ai": "утреннюю ИИ-сводку"}
    ctx.actions.append(f"подписал на {names[kind]} в {hour:02d}:{minute:02d} МСК")
    return f"Подписал на {names[kind]} — {hour:02d}:{minute:02d} МСК."


async def _tool_set_reminder(ctx: _Ctx, args: dict) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        return "Пустой текст напоминания."
    hour = int(args.get("hour") or 9)
    minute = int(args.get("minute") or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return "Некорректное время."
    now = datetime.now(timezone.utc)
    run_at = next_run("daily", hour, minute, now).replace(tzinfo=None)
    ctx.session.add(Reminder(user_tg_id=ctx.uid, text=text[:500], next_run_at=run_at))
    await ctx.session.commit()
    ctx.actions.append(f"поставил напоминание на {hour:02d}:{minute:02d}")
    return f"Напоминание поставлено на {hour:02d}:{minute:02d} МСК."


async def _user_channels(session: AsyncSession, uid: int) -> list[TrackedChat]:
    return (
        await session.scalars(
            select(TrackedChat).where(TrackedChat.added_by_tg_id == uid)
        )
    ).all()


async def _tool_list_channels(ctx: _Ctx, args: dict) -> str:
    chats = await _user_channels(ctx.session, ctx.uid)
    if not chats:
        return "Подключённых каналов нет. Добавь меня в канал/группу администратором."
    return "\n".join(f"- {c.title or c.chat_id} ({c.chat_type})" for c in chats)


async def _tool_set_voice(ctx: _Ctx, args: dict) -> str:
    description = str(args.get("description", "")).strip()
    if not description:
        return "Пустое описание тона."
    await set_voice(ctx.session, ctx.uid, description)
    ctx.actions.append("запомнил твой стиль")
    return f"Запомнил голос бренда: {description[:80]}. Буду писать в этом тоне."


async def _tool_post_to_channel(ctx: _Ctx, args: dict) -> str:
    channel = str(args.get("channel", "")).strip()
    text = str(args.get("text", "")).strip()
    if not text:
        return "Пустой текст поста."
    chats = await _user_channels(ctx.session, ctx.uid)
    if not chats:
        return "Нет подключённых каналов — добавь меня в канал администратором."
    target = None
    for c in chats:
        title = (c.title or "").lower()
        if channel.lower() in title or channel == str(c.chat_id):
            target = c
            break
    if target is None:
        return "Такой канал не найден. Посмотри list_channels и укажи название точнее."

    status = "ready" if ctx.level == "autopilot" else "pending"
    post = OutgoingPost(
        user_tg_id=ctx.uid,
        chat_id=target.chat_id,
        chat_title=target.title or str(target.chat_id),
        text=text,
        status=status,
    )
    ctx.session.add(post)
    await ctx.session.commit()
    await ctx.session.refresh(post)

    if status == "pending":
        ctx.pending_posts.append((post.id, post.chat_title, text[:80]))
        return f"Пост для «{post.chat_title}» подготовлен и ждёт подтверждения клиента."
    ctx.actions.append(f"выложу пост в «{post.chat_title}»")
    return f"Пост поставлен в очередь на публикацию в «{post.chat_title}»."


_TOOLS = {
    "get_panel": _tool_get_panel,
    "list_metrics": _tool_list_metrics,
    "add_metric": _tool_add_metric,
    "get_report": _tool_get_report,
    "get_table": _tool_get_table,
    "remember": _tool_remember,
    "set_alert": _tool_set_alert,
    "schedule_report": _tool_schedule_report,
    "set_reminder": _tool_set_reminder,
    "list_channels": _tool_list_channels,
    "set_voice": _tool_set_voice,
    "post_to_channel": _tool_post_to_channel,
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


async def _load_memory(session: AsyncSession, user_tg_id: int) -> str:
    """Персональная память клиента — подаётся в контекст перед вопросом."""
    facts = (
        await session.scalars(
            select(AgentMemory)
            .where(AgentMemory.user_tg_id == user_tg_id)
            .order_by(AgentMemory.created_at.desc())
            .limit(20)
        )
    ).all()
    if not facts:
        return ""
    lines = "\n".join(f"- {f.content}" for f in reversed(facts))
    return f"Что я помню о бизнесе клиента:\n{lines}\n\n"


async def run_agent(session: AsyncSession, user_tg_id: int, user_message: str) -> AgentResult:
    """Гоняет ИИ-оркестратор: думает, зовёт инструменты, отвечает."""
    if not settings.ai_enabled:
        return AgentResult(ai.DISABLED_MSG)
    level = await get_autonomy(session, user_tg_id)
    ctx = _Ctx(session=session, uid=user_tg_id, level=level)
    memory = await _load_memory(session, user_tg_id)
    voice = await get_voice(session, user_tg_id)
    if voice:
        memory += f"Голос бренда клиента (пиши посты и сообщения в этом тоне): {voice}\n\n"
    messages: list[dict] = [{"role": "user", "content": memory + user_message}]

    for _ in range(MAX_STEPS):
        try:
            response = await _create_message(messages)
        except Exception:
            logger.exception("Вызов модели упал для %s", user_tg_id)
            return AgentResult(ai.ERROR_MSG, actions=ctx.actions, pending=ctx.pending, pending_posts=ctx.pending_posts)

        if getattr(response, "stop_reason", None) != "tool_use":
            return AgentResult(_text_of(response), actions=ctx.actions, pending=ctx.pending, pending_posts=ctx.pending_posts)

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
        pending_posts=ctx.pending_posts,
    )
