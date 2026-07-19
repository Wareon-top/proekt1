"""Команда /pulse — «пульт»: движок метрик в боте.

Текстовый вход для проверки движка метрик прямо в Telegram. Финальный ИИ-первый
дашборд — отдельный шаг; здесь показываем метрики, тренды, точки роста / узкие
места и прогноз простым текстом."""

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from wareon.db.base import session_factory
from wareon.services.metrics import build_panel
from wareon.services.metrics.catalog import AREA_TITLES
from wareon.services.metrics.panel import (
    STATUS_BOTTLENECK,
    STATUS_GROWTH,
    STATUS_NA,
    Panel,
)

router = Router(name="pulse")

_STATUS_ICON = {
    STATUS_GROWTH: "📈",
    STATUS_BOTTLENECK: "⚠️",
    STATUS_NA: "·",
    "flat": "▪️",
}

PULSE_HELP = (
    "🎛 <b>Пульт</b> — метрики бизнеса за период.\n\n"
    "<code>/pulse</code> — за 7 дней\n"
    "<code>/pulse 30</code> — за 30 дней\n"
    "<code>/pulse 7 ad=3000 visitors=900</code> — донести рекламу и визиты "
    "(для ДРР, ROMI, конверсии)"
)

PULSE_EMPTY = (
    "🎛 <b>Пульт</b>\n\n"
    "Данных пока нет. Дай мне первую цифру — и я сразу покажу, где ты растёшь "
    "и где теряешь.\n\n"
    "➕ Запиши продажу: <code>/sale 15000 8000</code>"
)


def _parse_args(raw: str) -> tuple[int, dict[str, float]]:
    """Разбирает `7 ad=3000 visitors=900` → (days, manual). Бросает ValueError."""
    days = 7
    manual: dict[str, float] = {}
    for token in raw.split():
        if "=" in token:
            name, _, val = token.partition("=")
            manual[name.strip().lower()] = float(val.replace(",", "."))
        else:
            days = int(token)
    if not 1 <= days <= 365:
        raise ValueError("Период — от 1 до 365 дней")
    return days, manual


def _fmt_value(value: float | None, unit: str) -> str:
    if value is None:
        return "нет данных"
    if unit == "₽":
        return f"{value:,.0f} ₽".replace(",", " ")
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "шт":
        return f"{value:g} шт"
    return f"{value:g}"


def _fmt_trend(trend_pct: float | None) -> str:
    if trend_pct is None:
        return ""
    arrow = "▲" if trend_pct > 0 else "▼" if trend_pct < 0 else "="
    return f"  {arrow}{abs(trend_pct):.0f}%"


def panel_verdict(panel: Panel) -> str:
    """Короткий вердикт по пульту одной строкой (правило, без вызова ИИ)."""
    growth, bottleneck = bool(panel.growth_points), bool(panel.bottlenecks)
    if growth and bottleneck:
        return "📈 Растёшь — но есть узкие места."
    if growth:
        return "📈 Бизнес идёт в рост."
    if bottleneck:
        return "⚠️ Есть, что подтянуть."
    return "▪️ Пока ровно — мало данных для выводов."


def format_panel(panel: Panel) -> str:
    lines = [
        f"🎛 <b>Пульт · {panel.days} дн</b>  <i>(vs прошлые {panel.days})</i>",
        panel_verdict(panel) + "\n",
    ]

    # Показываем только посчитанные метрики — «нет данных» скрываем, чтобы не
    # засорять экран (донести рекламу/визиты можно через /pulse ad=.. visitors=..).
    visible = [m for m in panel.metrics if m.value is not None]
    hidden = len(panel.metrics) - len(visible)

    order: list[str] = []
    for m in visible:
        if m.area not in order:
            order.append(m.area)
    for area in order:
        lines.append(f"<b>{AREA_TITLES.get(area, area)}</b>")
        for m in (x for x in visible if x.area == area):
            icon = _STATUS_ICON.get(m.status, "▪️")
            tag = " 🤖" if m.custom else ""
            lines.append(f"{icon} {m.title}: {_fmt_value(m.value, m.unit)}{_fmt_trend(m.trend_pct)}{tag}")
        lines.append("")

    growth = panel.growth_points
    bottlenecks = panel.bottlenecks
    if growth:
        lines.append("📈 <b>Точки роста:</b> " + ", ".join(m.title for m in growth))
    if bottlenecks:
        lines.append("⚠️ <b>Узкие места:</b> " + ", ".join(m.title for m in bottlenecks))
    if panel.forecast_revenue is not None:
        lines.append(
            f"\n🔮 Прогноз выручки на следующие {panel.days} дн: "
            f"~{panel.forecast_revenue:,.0f} ₽".replace(",", " ")
        )
    if hidden:
        lines.append(
            f"\n<i>Ещё {hidden} метрик ждут данных о рекламе/визитах — "
            f"донести: <code>/pulse {panel.days} ad=3000 visitors=900</code></i>"
        )
    return "\n".join(lines).strip()


@router.message(Command("pulse"))
async def cmd_pulse(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    try:
        days, manual = _parse_args(command.args or "")
    except ValueError:
        await message.answer(PULSE_HELP)
        return

    async with session_factory() as session:
        panel = await build_panel(session, message.from_user.id, days=days, manual=manual)

    # Есть ли вообще продажи в периоде (по выручке).
    revenue = next((m for m in panel.metrics if m.key == "revenue"), None)
    if revenue is None or not revenue.value:
        await message.answer(PULSE_EMPTY)
        return

    await message.answer(format_panel(panel))
