from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable


Operator = Callable[["ExpressionEvaluator", dict[str, Any], dict[str, Any]], Any]


def resolve_path(source: Any, path: str, default: Any = None) -> Any:
    if path is None:
        return default
    if path == "":
        return source

    current = source
    for part in str(path).split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return default
            current = current[part]
            continue

        if isinstance(current, (list, tuple)):
            if not part.isdigit():
                return default
            index = int(part)
            if index < 0 or index >= len(current):
                return default
            current = current[index]
            continue

        if hasattr(current, part):
            current = getattr(current, part)
            continue

        return default

    return current


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def normalize_symbol_pool(pool: Any) -> list[str]:
    if pool is None:
        return []
    if isinstance(pool, str):
        tokens = [token for token in pool.replace(";", ",").replace(" ", ",").split(",") if token]
        return [normalize_symbol(token) for token in tokens if normalize_symbol(token)]
    if isinstance(pool, (list, tuple, set)):
        return [normalize_symbol(token) for token in pool if normalize_symbol(token)]
    return [normalize_symbol(pool)] if normalize_symbol(pool) else []


class ExpressionEvaluator:
    def __init__(self, operators: dict[str, Operator] | None = None) -> None:
        self._operators = dict(default_operators())
        if operators:
            self._operators.update(operators)

    def evaluate(self, expression: Any, context: dict[str, Any]) -> Any:
        if isinstance(expression, dict):
            if "var" in expression:
                return resolve_path(context, expression["var"], expression.get("default"))
            if "op" in expression:
                operator_name = str(expression["op"]).strip().lower()
                if operator_name not in self._operators:
                    raise KeyError(f"Unsupported rule operator: {operator_name}")
                return self._operators[operator_name](self, expression, context)
            return {key: self.evaluate(value, context) for key, value in expression.items()}

        if isinstance(expression, list):
            return [self.evaluate(item, context) for item in expression]

        return expression

    def render(self, value: Any, context: dict[str, Any]) -> Any:
        return self.evaluate(value, context)


def _binary_op(expression: dict[str, Any], evaluator: ExpressionEvaluator, context: dict[str, Any]) -> tuple[Any, Any]:
    left = evaluator.evaluate(expression.get("left"), context)
    right = evaluator.evaluate(expression.get("right"), context)
    return left, right


def _op_eq(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    left, right = _binary_op(expression, evaluator, context)
    return left == right


def _op_ne(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    left, right = _binary_op(expression, evaluator, context)
    return left != right


def _op_gt(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    left, right = _binary_op(expression, evaluator, context)
    return left > right


def _op_ge(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    left, right = _binary_op(expression, evaluator, context)
    return left >= right


def _op_lt(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    left, right = _binary_op(expression, evaluator, context)
    return left < right


def _op_le(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    left, right = _binary_op(expression, evaluator, context)
    return left <= right


def _op_all(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    conditions = expression.get("conditions", expression.get("value", []))
    if not isinstance(conditions, list):
        raise TypeError("all operator requires a list of conditions")
    return all(bool(evaluator.evaluate(condition, context)) for condition in conditions)


def _op_any(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    conditions = expression.get("conditions", expression.get("value", []))
    if not isinstance(conditions, list):
        raise TypeError("any operator requires a list of conditions")
    return any(bool(evaluator.evaluate(condition, context)) for condition in conditions)


def _op_not(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    return not bool(evaluator.evaluate(expression.get("value"), context))


def _op_in(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    item = evaluator.evaluate(expression.get("item", expression.get("left")), context)
    collection = evaluator.evaluate(expression.get("collection", expression.get("right")), context)
    if collection is None:
        return False
    if isinstance(collection, str):
        return str(item) in collection
    return item in collection


def _op_not_in(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    return not _op_in(evaluator, expression, context)


def _op_contains(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    haystack = evaluator.evaluate(expression.get("haystack", expression.get("left")), context)
    needle = evaluator.evaluate(expression.get("needle", expression.get("right")), context)
    if haystack is None:
        return False
    if isinstance(haystack, str):
        return str(needle) in haystack
    return needle in haystack


def _op_between(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    value = evaluator.evaluate(expression.get("value"), context)
    lower = evaluator.evaluate(expression.get("lower"), context)
    upper = evaluator.evaluate(expression.get("upper"), context)
    return lower <= value <= upper


def _op_exists(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    value = evaluator.evaluate(expression.get("value"), context)
    return value is not None


def _op_truthy(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    return bool(evaluator.evaluate(expression.get("value"), context))


def _op_symbol_in_pool(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    symbol = normalize_symbol(evaluator.evaluate(expression.get("symbol"), context))
    pool = normalize_symbol_pool(evaluator.evaluate(expression.get("pool"), context))
    return bool(symbol) and symbol in pool


def _op_is_trading_session(evaluator: ExpressionEvaluator, expression: dict[str, Any], context: dict[str, Any]) -> bool:
    session = evaluator.evaluate(expression.get("session", expression.get("value")), context)
    if isinstance(session, bool):
        return session
    if isinstance(session, Mapping):
        for key in ("sessionOpen", "isOpen", "open"):
            if key in session:
                return bool(session[key])
    return False


def default_operators() -> dict[str, Operator]:
    return {
        "eq": _op_eq,
        "ne": _op_ne,
        "gt": _op_gt,
        "ge": _op_ge,
        "gte": _op_ge,
        "lt": _op_lt,
        "le": _op_le,
        "lte": _op_le,
        "all": _op_all,
        "and": _op_all,
        "any": _op_any,
        "or": _op_any,
        "not": _op_not,
        "in": _op_in,
        "not_in": _op_not_in,
        "contains": _op_contains,
        "between": _op_between,
        "exists": _op_exists,
        "truthy": _op_truthy,
        "symbol_in_pool": _op_symbol_in_pool,
        "is_trading_session": _op_is_trading_session,
    }