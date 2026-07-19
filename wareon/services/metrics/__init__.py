"""Движок метрик Wareon — «пульт»: базовые переменные из данных клиента,
безопасные формулы, встроенный каталог, тренды и простой прогноз.

Фундамент под ИИ-оркестратора: и человек, и ИИ заводят метрики через один и тот
же безопасный механизм формул."""

from wareon.services.metrics.catalog import BUILTIN_METRICS, MetricDef, by_area
from wareon.services.metrics.formula import (
    FormulaError,
    compile_formula,
    evaluate,
    validate_expression,
)
from wareon.services.metrics.panel import (
    MetricValue,
    Panel,
    base_variables,
    build_panel,
    linear_forecast,
)

__all__ = [
    "BUILTIN_METRICS",
    "MetricDef",
    "by_area",
    "FormulaError",
    "compile_formula",
    "evaluate",
    "validate_expression",
    "MetricValue",
    "Panel",
    "base_variables",
    "build_panel",
    "linear_forecast",
]
