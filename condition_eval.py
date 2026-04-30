from __future__ import annotations

import ast
from typing import Any, Callable, Dict, List


class ConditionEvalError(ValueError):
    pass


class ConditionEvaluator:
    def evaluate_all(self, conditions: Any, ctx: Dict[str, Any]) -> bool:
        if not conditions:
            return True
        if not isinstance(conditions, list):
            raise ConditionEvalError("conditions must be a list of strings")
        for cond in conditions:
            if not isinstance(cond, str) or not cond.strip():
                continue
            if not self._eval_expr(cond.strip(), ctx):
                return False
        return True

    def _eval_expr(self, expr: str, ctx: Dict[str, Any]) -> bool:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ConditionEvalError(f"invalid condition expression: {expr}") from exc
        value = self._eval_node(tree.body, ctx)
        return bool(value)

    def _eval_node(self, node: ast.AST, ctx: Dict[str, Any]) -> Any:
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(bool(self._eval_node(v, ctx)) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(bool(self._eval_node(v, ctx)) for v in node.values)
            raise ConditionEvalError("unsupported boolean operator")

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not bool(self._eval_node(node.operand, ctx))
            raise ConditionEvalError("unsupported unary operator")

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, ctx)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval_node(comp, ctx)
                ok = self._compare(op, left, right)
                if not ok:
                    return False
                left = right
            return True

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ConditionEvalError("only simple function calls are allowed")
            func_name = node.func.id
            func = self._functions(ctx).get(func_name)
            if func is None:
                raise ConditionEvalError(f"unknown function: {func_name}")
            args = [self._eval_node(a, ctx) for a in node.args]
            if node.keywords:
                raise ConditionEvalError("keyword arguments are not supported")
            return func(*args)

        if isinstance(node, ast.Name):
            if node.id in ctx:
                return ctx[node.id]
            raise ConditionEvalError(f"unknown name: {node.id}")

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.List):
            return [self._eval_node(elt, ctx) for elt in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt, ctx) for elt in node.elts)

        raise ConditionEvalError(f"unsupported expression: {type(node).__name__}")

    def _compare(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.In):
            try:
                return left in right
            except TypeError:
                return False
        if isinstance(op, ast.NotIn):
            try:
                return left not in right
            except TypeError:
                return False
        raise ConditionEvalError("unsupported comparison operator")

    def _functions(self, ctx: Dict[str, Any]) -> Dict[str, Callable[..., Any]]:
        intentions = ctx.get("intentions", [])
        slot_statuses = ctx.get("slot_statuses", [])

        def has_intention(name: Any) -> bool:
            return str(name) in {str(x) for x in intentions if x is not None}

        def slot_status_any_of(status_list: Any) -> bool:
            if not isinstance(status_list, list):
                return False
            allowed = {str(x) for x in status_list if x is not None}
            return any(str(s) in allowed for s in slot_statuses if s is not None)

        def slot_status_all_in(status_list: Any) -> bool:
            if not isinstance(status_list, list):
                return False
            allowed = {str(x) for x in status_list if x is not None}
            normalized = [str(s) for s in slot_statuses if s is not None]
            return bool(normalized) and all(s in allowed for s in normalized)

        return {
            "has_intention": has_intention,
            "slot_status_any_of": slot_status_any_of,
            "slot_status_all_in": slot_status_all_in,
        }

