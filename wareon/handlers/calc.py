"""Калькуляторы на кнопках со свободным пошаговым вводом.

Вместо длинных списков команд — кнопка калькулятора запускает диалог: бот
спрашивает числа по одному, ты просто пишешь их, в конце — результат. Один
общий FSM-движок обслуживает все калькуляторы (описаны данными в CALCULATORS)."""

from dataclasses import dataclass
from typing import Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from wareon.keyboards import back_menu
from wareon.services import analytics

router = Router(name="calc")


class Calc(StatesGroup):
    collecting = State()


@dataclass
class Field:
    label: str      # что спрашиваем (с единицей)
    name: str       # ключ значения


@dataclass
class Calculator:
    key: str
    emoji: str
    title: str
    fields: list[Field]
    compute: Callable[[dict], str]


def _m(v: float) -> str:
    return f"{round(v):,} ₽".replace(",", " ")


# ── Формулы результата (используют проверенные функции analytics) ─────────────
def _profit(v):
    r = analytics.profit_report(v["revenue"], v["cost"])
    return (
        f"Выручка: {_m(r.revenue)}\nСебестоимость: {_m(r.cost)}\n"
        f"Прибыль: <b>{_m(r.profit)}</b>\nМаржа: {r.margin_pct}%\nНаценка: {r.markup_pct}%"
    )


def _conversion(v):
    return f"Конверсия: <b>{analytics.conversion(int(v['visitors']), int(v['actions']))}%</b>"


def _avg(v):
    return f"Средний чек: <b>{_m(analytics.average_check(v['revenue'], int(v['orders'])))}</b>"


def _roi(v):
    return f"ROI: <b>{analytics.roi(v['profit'], v['investment'])}%</b>"


def _romi(v):
    return f"ROMI: <b>{analytics.romi(v['ad_revenue'], v['ad_spend'])}%</b>"


def _breakeven(v):
    u = analytics.breakeven_units(v["fixed"], v["price"], v["variable"])
    return f"Точка безубыточности: <b>{u} шт</b> — столько продать, чтобы выйти в ноль."


def _salary(v):
    s = analytics.salary(v["fixed"], v["volume"], v["percent"], v["bonus"])
    return (
        f"Начислено: {_m(s.gross)}\nНДФЛ 13%: {_m(s.ndfl)}\nНа руки: <b>{_m(s.net)}</b>"
    )


def _unit(v):
    u = analytics.marketplace_unit(v["price"], v["commission"], v["logistics"], v["cost"], v["ad"])
    return (
        f"Комиссия: {_m(u.commission)}\n"
        f"Прибыль с продажи: <b>{_m(u.profit_per_unit)}</b>\nМаржа: {u.margin_pct}%"
    )


def _card(v):
    c = analytics.card_funnel(
        int(v["impressions"]), int(v["clicks"]), int(v["carts"]), int(v["orders"])
    )
    return (
        f"CTR (показы→клики): {c.ctr_pct}%\nКлики→корзина: {c.cart_pct}%\n"
        f"Корзина→заказ: {c.order_pct}%\nПоказы→заказ: <b>{c.total_pct}%</b>"
    )


CALCULATORS: dict[str, Calculator] = {
    c.key: c
    for c in [
        Calculator("profit", "💰", "Прибыль и маржа",
                   [Field("Выручка, ₽", "revenue"), Field("Себестоимость, ₽", "cost")], _profit),
        Calculator("conversion", "🎯", "Конверсия",
                   [Field("Посетителей", "visitors"), Field("Покупок / целевых действий", "actions")],
                   _conversion),
        Calculator("avg", "🧾", "Средний чек",
                   [Field("Выручка, ₽", "revenue"), Field("Число заказов", "orders")], _avg),
        Calculator("roi", "📈", "ROI",
                   [Field("Прибыль, ₽", "profit"), Field("Вложения, ₽", "investment")], _roi),
        Calculator("romi", "📣", "ROMI",
                   [Field("Доход с рекламы, ₽", "ad_revenue"), Field("Рекламный бюджет, ₽", "ad_spend")],
                   _romi),
        Calculator("breakeven", "⚖️", "Точка безубыточности",
                   [Field("Постоянные затраты, ₽", "fixed"), Field("Цена за единицу, ₽", "price"),
                    Field("Переменные затраты на единицу, ₽", "variable")], _breakeven),
        Calculator("salary", "👤", "Зарплата менеджера",
                   [Field("Оклад, ₽", "fixed"), Field("Объём продаж, ₽", "volume"),
                    Field("Процент с продаж, %", "percent"), Field("Бонус, ₽", "bonus")], _salary),
        Calculator("unit", "🛍", "Юнит-экономика (маркетплейс)",
                   [Field("Цена, ₽", "price"), Field("Комиссия площадки, %", "commission"),
                    Field("Логистика, ₽", "logistics"), Field("Себестоимость, ₽", "cost"),
                    Field("Реклама на единицу, ₽", "ad")], _unit),
        Calculator("card", "🃏", "Воронка карточки",
                   [Field("Показы", "impressions"), Field("Клики", "clicks"),
                    Field("Добавления в корзину", "carts"), Field("Заказы", "orders")], _card),
    ]
}

CALC_INTRO = (
    "🧮 <b>Калькуляторы</b>\n\n"
    "Выбери расчёт — я спрошу числа по одному, тебе останется их вписать."
)


def calc_menu_kb() -> InlineKeyboardMarkup:
    items = list(CALCULATORS.values())
    rows, row = [], []
    for c in items:
        row.append(InlineKeyboardButton(text=f"{c.emoji} {c.title}", callback_data=f"calc:go:{c.key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="calc:cancel")]]
    )


def _after_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Ещё раз", callback_data=f"calc:go:{key}"),
                InlineKeyboardButton(text="🧮 Калькуляторы", callback_data="menu:calc"),
            ]
        ]
    )


def _prompt(calc: Calculator, idx: int) -> str:
    field = calc.fields[idx]
    return (
        f"{calc.emoji} <b>{calc.title}</b>  <i>шаг {idx + 1}/{len(calc.fields)}</i>\n\n"
        f"Введи: <b>{field.label}</b>"
    )


@router.callback_query(F.data == "menu:calc")
async def open_calc(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(CALC_INTRO, reply_markup=calc_menu_kb())
        except Exception:
            await callback.message.answer(CALC_INTRO, reply_markup=calc_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("calc:go:"))
async def start_calc(callback: CallbackQuery, state: FSMContext) -> None:
    key = (callback.data or "").split(":", 2)[2]
    calc = CALCULATORS.get(key)
    if calc is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(Calc.collecting)
    await state.update_data(key=key, idx=0, values={})
    try:
        await callback.message.edit_text(_prompt(calc, 0), reply_markup=_cancel_kb())
    except Exception:
        await callback.message.answer(_prompt(calc, 0), reply_markup=_cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "calc:cancel")
async def cancel_calc(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(CALC_INTRO, reply_markup=calc_menu_kb())
        except Exception:
            pass
    await callback.answer("Отменено")


@router.message(Calc.collecting)
async def collect(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    calc = CALCULATORS[data["key"]]
    idx = data["idx"]
    field = calc.fields[idx]

    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        num = float(raw)
        if num < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            f"Нужно неотрицательное число.\n\n{_prompt(calc, idx)}", reply_markup=_cancel_kb()
        )
        return

    values = dict(data["values"])
    values[field.name] = num
    idx += 1

    if idx < len(calc.fields):
        await state.update_data(idx=idx, values=values)
        await message.answer(_prompt(calc, idx), reply_markup=_cancel_kb())
        return

    await state.clear()
    try:
        body = calc.compute(values)
    except ValueError as exc:
        await message.answer(
            f"⚠️ {exc}\nПроверь числа и запусти расчёт заново.", reply_markup=calc_menu_kb()
        )
        return
    await message.answer(
        f"{calc.emoji} <b>{calc.title}</b>\n<blockquote>{body}</blockquote>",
        reply_markup=_after_kb(calc.key),
    )
