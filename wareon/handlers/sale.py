"""Пошаговый ввод продажи кнопкой (без команды): выручка → себестоимость →
источник. Тот же удобный подход, что и калькуляторы."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from wareon.db.base import session_factory
from wareon.db.models import Sale
from wareon.keyboards import back_menu

router = Router(name="sale")


class SaleFlow(StatesGroup):
    revenue = State()
    cost = State()
    source = State()


def _kb(skip: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if skip:
        rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data="sale:skip")])
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="sale:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _num(text: str | None) -> float:
    return float((text or "").strip().replace(" ", "").replace(",", "."))


def _money(v: float) -> str:
    return f"{round(v):,} ₽".replace(",", " ")


@router.callback_query(F.data == "sale:start")
async def start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SaleFlow.revenue)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                "➕ <b>Новая продажа</b>  <i>шаг 1/3</i>\n\nВыручка, ₽?", reply_markup=_kb()
            )
        except Exception:
            await callback.message.answer(
                "➕ <b>Новая продажа</b>  <i>шаг 1/3</i>\n\nВыручка, ₽?", reply_markup=_kb()
            )
    await callback.answer()


@router.message(SaleFlow.revenue)
async def step_revenue(message: Message, state: FSMContext) -> None:
    try:
        v = _num(message.text)
        if v < 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно неотрицательное число.\nВыручка, ₽?", reply_markup=_kb())
        return
    await state.update_data(revenue=v)
    await state.set_state(SaleFlow.cost)
    await message.answer(
        "➕ <b>Новая продажа</b>  <i>шаг 2/3</i>\n\nСебестоимость, ₽? (0 — если не считаешь)",
        reply_markup=_kb(),
    )


@router.message(SaleFlow.cost)
async def step_cost(message: Message, state: FSMContext) -> None:
    try:
        v = _num(message.text)
        if v < 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно неотрицательное число.\nСебестоимость, ₽?", reply_markup=_kb())
        return
    await state.update_data(cost=v)
    await state.set_state(SaleFlow.source)
    await message.answer(
        "➕ <b>Новая продажа</b>  <i>шаг 3/3</i>\n\nОткуда продажа? (сайт, авито…) "
        "— или ⏭ Пропустить",
        reply_markup=_kb(skip=True),
    )


@router.message(SaleFlow.source)
async def step_source(message: Message, state: FSMContext) -> None:
    source = (message.text or "").strip() or None
    await _save(message, state, source, message.from_user.id if message.from_user else 0)


@router.callback_query(F.data == "sale:skip")
async def skip_source(callback: CallbackQuery, state: FSMContext) -> None:
    if isinstance(callback.message, Message) and callback.from_user:
        await _save(callback.message, state, None, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "sale:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text("Отменено.", reply_markup=back_menu())
        except Exception:
            pass
    await callback.answer("Отменено")


async def _save(message: Message, state: FSMContext, source: str | None, uid: int) -> None:
    data = await state.get_data()
    await state.clear()
    revenue = float(data.get("revenue", 0.0))
    cost = float(data.get("cost", 0.0))
    async with session_factory() as session:
        session.add(Sale(user_tg_id=uid, revenue=revenue, cost=cost, source=source))
        await session.commit()
    profit = revenue - cost
    text = (
        f"✅ Записал: выручка {_money(revenue)}, прибыль <b>{_money(profit)}</b>"
        + (f", источник — {source}" if source else "")
        + "\n\nЖми 🎛 Пульт — покажу тренды."
    )
    await message.answer(text, reply_markup=back_menu())
