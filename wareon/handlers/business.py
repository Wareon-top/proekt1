from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from wareon.db.base import session_factory
from wareon.db.models import Sale
from wareon.services import analytics

router = Router(name="business")


def _floats(command: CommandObject, count_min: int, count_max: int | None = None) -> list[float]:
    args = (command.args or "").split()
    if count_max is None:
        count_max = count_min
    if not count_min <= len(args) <= count_max:
        raise ValueError
    return [float(a.replace(",", ".")) for a in args]


@router.message(Command("sale"))
async def cmd_sale(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()
    if not args or message.from_user is None:
        await message.answer(
            "Формат: <code>/sale выручка [себестоимость] [источник]</code>\n"
            "Например: <code>/sale 15000 8000 сайт</code>"
        )
        return
    try:
        revenue = float(args[0].replace(",", "."))
        cost = float(args[1].replace(",", ".")) if len(args) > 1 else 0.0
        if revenue < 0 or cost < 0:
            raise ValueError
    except ValueError:
        await message.answer("Не понял числа. Пример: <code>/sale 15000 8000 сайт</code>")
        return
    source = " ".join(args[2:]) if len(args) > 2 else None

    async with session_factory() as session:
        session.add(
            Sale(user_tg_id=message.from_user.id, revenue=revenue, cost=cost, source=source)
        )
        await session.commit()

    profit = revenue - cost
    await message.answer(
        f"✅ Продажа записана: выручка {revenue:,.2f} ₽, "
        f"прибыль {profit:,.2f} ₽"
        + (f", источник — {source}" if source else "")
        + "\n\nСводка за период: /report"
    )


@router.message(Command("profit"))
async def cmd_profit(message: Message, command: CommandObject) -> None:
    try:
        revenue, cost = _floats(command, 2)
        r = analytics.profit_report(revenue, cost)
    except ValueError:
        await message.answer("Формат: <code>/profit выручка себестоимость</code>")
        return
    await message.answer(
        f"💰 Выручка: {r.revenue:,.2f} ₽\n"
        f"📦 Себестоимость: {r.cost:,.2f} ₽\n"
        f"📈 Прибыль: {r.profit:,.2f} ₽\n"
        f"Маржинальность: {r.margin_pct}%\n"
        f"Наценка: {r.markup_pct}%"
    )


@router.message(Command("conversion"))
async def cmd_conversion(message: Message, command: CommandObject) -> None:
    try:
        visitors, actions = _floats(command, 2)
        value = analytics.conversion(int(visitors), int(actions))
    except ValueError:
        await message.answer("Формат: <code>/conversion посетители действия</code>")
        return
    await message.answer(f"🎯 Конверсия: <b>{value}%</b> ({int(actions)} из {int(visitors)})")


@router.message(Command("avg"))
async def cmd_avg(message: Message, command: CommandObject) -> None:
    try:
        revenue, orders = _floats(command, 2)
        value = analytics.average_check(revenue, int(orders))
    except ValueError:
        await message.answer("Формат: <code>/avg выручка количество_заказов</code>")
        return
    await message.answer(f"🧾 Средний чек: <b>{value:,.2f} ₽</b>")


@router.message(Command("roi"))
async def cmd_roi(message: Message, command: CommandObject) -> None:
    try:
        profit, investment = _floats(command, 2)
        value = analytics.roi(profit, investment)
    except ValueError:
        await message.answer("Формат: <code>/roi прибыль вложения</code>")
        return
    verdict = "вложения окупаются ✅" if value > 0 else "вложения пока не окупаются ⚠️"
    await message.answer(f"📊 ROI: <b>{value}%</b> — {verdict}")


@router.message(Command("romi"))
async def cmd_romi(message: Message, command: CommandObject) -> None:
    try:
        ad_revenue, ad_spend = _floats(command, 2)
        value = analytics.romi(ad_revenue, ad_spend)
    except ValueError:
        await message.answer("Формат: <code>/romi доход_с_рекламы рекламный_бюджет</code>")
        return
    verdict = "реклама прибыльна ✅" if value > 0 else "реклама убыточна ⚠️"
    await message.answer(f"📣 ROMI: <b>{value}%</b> — {verdict}")


@router.message(Command("breakeven"))
async def cmd_breakeven(message: Message, command: CommandObject) -> None:
    try:
        fixed, price, variable = _floats(command, 3)
        units = analytics.breakeven_units(fixed, price, variable)
    except ValueError:
        await message.answer(
            "Формат: <code>/breakeven пост_затраты цена перем_затраты_на_ед</code>"
        )
        return
    await message.answer(
        f"⚖️ Точка безубыточности: <b>{units} шт.</b>\n"
        f"Продайте столько единиц, чтобы покрыть {fixed:,.2f} ₽ постоянных затрат."
    )


@router.message(Command("salary"))
async def cmd_salary(message: Message, command: CommandObject) -> None:
    try:
        values = _floats(command, 1, 4)
        r = analytics.salary(*values)
    except ValueError:
        await message.answer(
            "Формат: <code>/salary оклад [объём_продаж] [процент] [бонус]</code>\n"
            "Например: <code>/salary 50000 800000 5 10000</code>"
        )
        return
    await message.answer(
        f"💵 Начислено: {r.gross:,.2f} ₽\n"
        f"НДФЛ (13%): {r.ndfl:,.2f} ₽\n"
        f"На руки: <b>{r.net:,.2f} ₽</b>"
    )


@router.message(Command("funnel"))
async def cmd_funnel(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()
    stages: list[tuple[str, int]] = []
    try:
        for a in args:
            name, _, num = a.rpartition(":")
            stages.append((name or f"этап {len(stages) + 1}", int(num)))
        result = analytics.funnel(stages)
    except ValueError:
        await message.answer(
            "Формат: <code>/funnel показы:10000 клики:800 заказы:56</code>\n"
            "Минимум два этапа, каждый как <code>название:число</code>."
        )
        return
    lines = ["🔻 <b>Воронка продаж</b>", ""]
    for st in result:
        lines.append(
            f"• {st.name}: {st.count} "
            f"(от предыдущего {st.conversion_from_prev_pct}%, от первого "
            f"{st.conversion_from_first_pct}%)"
        )
    worst = min(result[1:], key=lambda s: s.conversion_from_prev_pct, default=None)
    if worst:
        lines.append("")
        lines.append(
            f"💡 Самое узкое место — переход к «{worst.name}» "
            f"({worst.conversion_from_prev_pct}%). Начните оптимизацию с него."
        )
    await message.answer("\n".join(lines))
