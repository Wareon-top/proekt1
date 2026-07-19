"""Безопасный движок формул для метрик.

Формула метрики — это арифметическое выражение над базовыми переменными
(revenue, cost, orders, ...). Разбираем через `ast` и разрешаем только числа,
имена переменных и операции + - * / % ** со скобками. Никакого `eval` и никакого
доступа к атрибутам/вызовам — это принцип «Безопасно» из конституции: и человек,
и ИИ задают метрику из одних и тех же кирпичиков, без произвольного кода.
"""

import ast
import operator
from functools import lru_cache

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# Узлы, допустимые в дереве формулы (структурная проверка при заведении метрики).
_ALLOWED_NODES: tuple = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Constant,
    ast.Load,
    *_BINOPS,
    *_UNARYOPS,
)

_MAX_LEN = 256


class FormulaError(ValueError):
    """Формула некорректна или содержит запрещённые конструкции."""


class _Unavailable(Exception):
    """Внутренний сигнал: значение посчитать нельзя (нет переменной / деление на 0)."""


def compile_formula(expr: str) -> ast.Expression:
    """Разбирает и проверяет формулу. Бросает FormulaError, если что-то не так."""
    if not expr or not expr.strip():
        raise FormulaError("Пустая формула")
    if len(expr) > _MAX_LEN:
        raise FormulaError("Слишком длинная формула")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Синтаксическая ошибка: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"Недопустимый элемент: {type(node).__name__}")
        if isinstance(node, ast.Constant) and (
            isinstance(node.value, bool) or not isinstance(node.value, (int, float))
        ):
            raise FormulaError("В формуле разрешены только числа")
    return tree


@lru_cache(maxsize=512)
def _cached_compile(expr: str) -> ast.Expression:
    return compile_formula(expr)


def variables_in(expr: str) -> set[str]:
    """Имена переменных, которые использует формула."""
    tree = _cached_compile(expr)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def validate_expression(expr: str, allowed: set[str] | None = None) -> None:
    """Проверяет формулу при заведении метрики. Если задан `allowed` — все
    переменные должны быть из этого набора. Бросает FormulaError при ошибке."""
    compile_formula(expr)
    if allowed is not None:
        unknown = variables_in(expr) - allowed
        if unknown:
            raise FormulaError("Неизвестные переменные: " + ", ".join(sorted(unknown)))


def _eval(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, variables)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise _Unavailable
        return float(variables[node.id])
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise FormulaError("Недопустимая операция")
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        if op in (operator.truediv, operator.mod) and right == 0:
            raise _Unavailable
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if op is None:
            raise FormulaError("Недопустимая операция")
        return op(_eval(node.operand, variables))
    raise FormulaError(f"Недопустимый элемент: {type(node).__name__}")


def evaluate(expr: str, variables: dict[str, float]) -> float | None:
    """Считает формулу на данных. Возвращает число или None, если посчитать
    нельзя (не хватает переменной или деление на ноль). FormulaError бросается
    только при по-настоящему некорректной формуле."""
    tree = _cached_compile(expr)
    try:
        return _eval(tree, variables)
    except _Unavailable:
        return None
