"""Пульт: премиальная подача — фирменный график + сжатая подпись, переключение
периода на месте, полный список метрик по кнопке."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from wareon.db.base import session_factory
from wareon.services import charts
from wareon.services.metrics import build_panel
from wareon.services.metrics.catalog import AREA_TITLES
from wareon.services.metrics.panel import STATUS_BOTTLENECK, STATUS_GROWTH, STATUS_NA, Panel

router = Router(name="pulse")

_STATUS_ICON = {STATUS_GROWTH: "📈", STATUS_BOTTLENECK: "⚠️", STATUS_NA: "·", "flat": "▪️"}

PULSE_HELP = (
    "🎛 <b>Пульт</b> — метрики бизнеса за период.\n\n"
    "<code>/pulse</code> — за 7 дней · <code>/pulse 30</code> — за 30\n"
    "<code>/pulse 7 ad=3000 visitors=900</code> — донести рекламу и визиты"
)

PULSE_EMPTY = (
    "🎛 <b>Пульт</b>\n\n"
    "Данных пока нет. Дай первую цифру — и я сразу покажу, где ты растёшь.\n\n"
    "➕ Запиши продажу: <code>/sale 15000 8000</code>"
)


def _parse_args(raw: str) -> tuple[int, dict[str, float]]:
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


def _num(value: float | None, unit: str) -> str:
    if value is None:
        return "нет данных"
    if unit == "₽":
        return f"{value:,.0f} ₽".replace(",", " ")
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "шт":
        return f"{value:g} шт"
    return f"{value:g}"


def _trend(pct: float | None) -> str:
    if pct is None:
        return ""
    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "="
    return f"  {arrow}{abs(pct):.0f}%"


def panel_verdict(panel: Panel) -> tuple[str, str]:
    growth, bottleneck = bool(panel.growth_points), bool(panel.bottlenecks)
    if growth and bottleneck:
        return "📈", "Растёшь — но есть узкие места."
    if growth:
        return "📈", "Бизнес идёт в рост."
    if bottleneck:
        return "⚠️", "Есть, что подтянуть."
    return "▪️", "Пока ровно — мало данных."


def _metric(panel: Panel, key: str):
    return next((m for m in panel.metrics if m.key == key), None)


def pulse_caption(panel: Panel) -> str:
    """Сжатая премиальная подпись под графиком (умещается в лимит подписи)."""
    em, verdict = panel_verdict(panel)
    lines = [f"🎛 <b>Пульт · {panel.days} дн</b>", f"{em} {verdict}", ""]

    for icon, key in [("💰", "revenue"), ("📊", "profit"), ("⚖️", "margin_pct")]:
        m = _metric(panel, key)
        if m and m.value is not None:
            lines.append(f"{icon} {m.title} — <b>{_num(m.value, m.unit)}</b>{_trend(m.trend_pct)}")

    growth = [m.title for m in panel.growth_points][:4]
    if growth:
        lines.append("\n📈 <b>Рост:</b> " + ", ".join(growth))
    bottlenecks = [m.title for m in panel.bottlenecks]
    if bottlenecks:
        lines.append("⚠️ <b>Узко:</b> " + ", ".join(bottlenecks))
    if panel.forecast_revenue is not None:
        lines.append(
            f"\n🔮 Прогноз {panel.days} дн: <b>~{panel.forecast_revenue:,.0f} ₽</b>".replace(",", " ")
        )
    return "\n".join(lines)


def format_panel(panel: Panel) -> str:
    """Полный список метрик по областям (для кнопки «Все метрики»)."""
    em, verdict = panel_verdict(panel)
    lines = [f"🎛 <b>Пульт · {panel.days} дн</b>", f"{em} {verdict}\n"]
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
            lines.append(f"{icon} {m.title}: {_num(m.value, m.unit)}{_trend(m.trend_pct)}{tag}")
        lines.append("")
    if hidden:
        lines.append(
            f"<i>Ещё {hidden} метрик ждут данных о рекламе/визитах — "
            f"<code>/pulse {panel.days} ad=3000 visitors=900</code></i>"
        )
    return "\n".join(lines).strip()


def _kb(days: int) -> InlineKeyboardMarkup:
    def p(d):
        return ("✅ " if d == days else "") + f"{d} дн"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=p(7), callback_data="pulse:7"),
                InlineKeyboardButton(text=p(30), callback_data="pulse:30"),
            ],
            [InlineKeyboardButton(text="📋 Все метрики", callback_data="pulse:all")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
        ]
    )


def _has_data(panel: Panel) -> bool:
    rev = _metric(panel, "revenue")
    return bool(rev and rev.value)


# ── /pulse ────────────────────────────────────────────────────────────────────
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
    if not _has_data(panel):
        await message.answer(PULSE_EMPTY)
        return
    chart = charts.pulse_chart_png(panel.revenue_series, days)
    if chart:
        await message.answer_photo(
            BufferedInputFile(chart, "pulse.png"), caption=pulse_caption(panel), reply_markup=_kb(days)
        )
    else:
        await message.answer(pulse_caption(panel), reply_markup=_kb(days))


# ── Пульт из меню (новое фото) ────────────────────────────────────────────────
@router.callback_query(F.data == "menu:pulse")
async def cb_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    async with session_factory() as session:
        panel = await build_panel(session, callback.from_user.id, days=7)
    if not _has_data(panel):
        await callback.message.answer(PULSE_EMPTY)
        await callback.answer()
        return
    chart = charts.pulse_chart_png(panel.revenue_series, 7)
    if chart:
        await callback.message.answer_photo(
            BufferedInputFile(chart, "pulse.png"), caption=pulse_caption(panel), reply_markup=_kb(7)
        )
    else:
        await callback.message.answer(pulse_caption(panel), reply_markup=_kb(7))
    await callback.answer()


# ── Переключение периода (на месте) и полный список ────────────────────────────
@router.callback_query(F.data.startswith("pulse:"))
async def cb_pulse_action(callback: CallbackQuery) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    part = (callback.data or "pulse:7").split(":", 1)[1]

    if part == "all":
        async with session_factory() as session:
            panel = await build_panel(session, callback.from_user.id, days=7)
        await callback.message.answer(format_panel(panel), reply_markup=_kb(7))
        await callback.answer()
        return

    try:
        days = int(part)
    except ValueError:
        await callback.answer()
        return
    async with session_factory() as session:
        panel = await build_panel(session, callback.from_user.id, days=days)
    chart = charts.pulse_chart_png(panel.revenue_series, days)
    if chart:
        try:
            await callback.message.edit_media(
                InputMediaPhoto(
                    media=BufferedInputFile(chart, "pulse.png"),
                    caption=pulse_caption(panel),
                    parse_mode="HTML",
                ),
                reply_markup=_kb(days),
            )
        except Exception:
            await callback.message.answer_photo(
                BufferedInputFile(chart, "pulse.png"),
                caption=pulse_caption(panel),
                reply_markup=_kb(days),
            )
    else:
        await callback.message.answer(pulse_caption(panel), reply_markup=_kb(days))
    await callback.answer()
