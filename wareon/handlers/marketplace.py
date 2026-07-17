from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from wareon.services import analytics

router = Router(name="marketplace")


@router.message(Command("card"))
async def cmd_card(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()
    try:
        if len(args) not in (4, 6):
            raise ValueError
        impressions, clicks, carts, orders = (int(a) for a in args[:4])
        ad_spend = float(args[4].replace(",", ".")) if len(args) == 6 else None
        revenue = float(args[5].replace(",", ".")) if len(args) == 6 else None
        f = analytics.card_funnel(impressions, clicks, carts, orders, ad_spend, revenue)
    except ValueError:
        await message.answer(
            "Формат: <code>/card показы клики корзины заказы [расход_рекламы выручка]</code>\n"
            "Например: <code>/card 50000 2500 400 120</code>"
        )
        return

    lines = [
        "🛍 <b>Воронка карточки</b>",
        "",
        f"👁 CTR (показы → клики): <b>{f.ctr_pct}%</b>",
        f"🛒 Клики → корзина: <b>{f.cart_pct}%</b>",
        f"📦 Корзина → заказ: <b>{f.order_pct}%</b>",
        f"🎯 Итого (показы → заказ): <b>{f.total_pct}%</b>",
    ]
    if f.drr_pct is not None:
        lines.append(f"📣 ДРР: <b>{f.drr_pct}%</b>")

    tips = []
    if f.ctr_pct < 3:
        tips.append("CTR ниже 3% — работайте над главным фото и ценой на карточке.")
    if f.cart_pct < 8:
        tips.append("Мало добавлений в корзину — усильте контент: фото, инфографику, отзывы.")
    if f.order_pct < 30:
        tips.append("Корзина плохо конвертируется в заказ — проверьте цену и сроки доставки.")
    if f.drr_pct is not None and f.drr_pct > 15:
        tips.append("ДРР выше 15% — реклама съедает маржу, оптимизируйте кампании.")
    if tips:
        lines.append("")
        lines.append("💡 " + "\n💡 ".join(tips))
    await message.answer("\n".join(lines))


@router.message(Command("unit"))
async def cmd_unit(message: Message, command: CommandObject) -> None:
    args = (command.args or "").split()
    try:
        if len(args) not in (4, 5):
            raise ValueError
        values = [float(a.replace(",", ".")) for a in args]
        u = analytics.marketplace_unit(*values)
    except ValueError:
        await message.answer(
            "Формат: <code>/unit цена комиссия% логистика себестоимость [реклама_на_ед]</code>\n"
            "Например: <code>/unit 1500 20 80 600 50</code>"
        )
        return
    verdict = (
        "✅ Юнит прибыльный" if u.profit_per_unit > 0 else "⚠️ Юнит убыточный — пересмотрите цену"
    )
    await message.answer(
        f"🧮 <b>Юнит-экономика</b>\n\n"
        f"Цена: {u.price:,.2f} ₽\n"
        f"Комиссия МП: {u.commission:,.2f} ₽\n"
        f"Логистика: {u.logistics:,.2f} ₽\n"
        f"Себестоимость: {u.cost:,.2f} ₽\n"
        f"Реклама на ед.: {u.ad_per_unit:,.2f} ₽\n\n"
        f"Прибыль с единицы: <b>{u.profit_per_unit:,.2f} ₽</b> (маржа {u.margin_pct}%)\n"
        f"{verdict}"
    )
