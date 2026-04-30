from __future__ import annotations

from typing import Any, Dict, List

from condition_eval import ConditionEvaluator


class ActsPlanner:
    """Pure package-driven act planner.

    It reads only generic planner metadata from act_catalog and checkpoint_catalog.
    No package-specific ids or names are hardcoded.
    """

    def plan(
        self,
        interaction_ir: Dict[str, Any],
        parse_result: Dict[str, Any],
        slot_update_result: Dict[str, Any],
        policy_result: Dict[str, Any],
        domain_package: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_checkpoint = str(interaction_ir.get("current_checkpoint") or "")
        intentions = [str(x) for x in parse_result.get("parsed_intentions", []) if x is not None]
        completion_state = str(policy_result.get("completion_state") or "not_ready")
        status_groups = self._build_status_groups(interaction_ir, slot_update_result)
        evaluator = ConditionEvaluator()
        ctx = {
            "checkpoint": current_checkpoint,
            "intentions": intentions,
            "slot_statuses": [str(slot.get("status") or "") for slot in interaction_ir.get("slots", []) if isinstance(slot, dict)],
            "completion_state": completion_state,
        }

        preferred_act_types: List[str] = []
        for checkpoint in domain_package.get("checkpoint_catalog", []):
            if isinstance(checkpoint, dict) and str(checkpoint.get("checkpoint_id") or "") == current_checkpoint:
                preferred_act_types = self._normalize_id_list(checkpoint.get("preferred_act_types", []), "act_type")
                break

        act_catalog = [a for a in domain_package.get("act_catalog", []) if isinstance(a, dict) and self._extract_id(a, "act_type")]
        by_type = {self._extract_id(a, "act_type"): a for a in act_catalog}

        matched_types_in_order: List[str] = []

        def matches(act: Dict[str, Any]) -> bool:
            planner = act.get("planner", {}) if isinstance(act.get("planner", {}), dict) else {}
            when = planner.get("when", {}) if isinstance(planner.get("when", {}), dict) else {}
            conditions = when.get("conditions", [])
            return evaluator.evaluate_all(conditions, ctx)

        for act_type in preferred_act_types:
            act = by_type.get(act_type)
            if not act:
                continue
            if matches(act):
                matched_types_in_order.append(act_type)

        for act in act_catalog:
            act_type = self._extract_id(act, "act_type")
            if act_type in matched_types_in_order:
                continue
            if matches(act):
                matched_types_in_order.append(act_type)

        if not matched_types_in_order:
            return {"selected_act_type": None, "focus_slot_ids": [], "candidate_act_types": [], "is_completion": False}

        best_act_type = matched_types_in_order[0]
        best_act = by_type[best_act_type]
        best_focus_ids = self._resolve_focus_ids(best_act.get("planner", {}), status_groups)
        return {
            "selected_act_type": best_act_type,
            "focus_slot_ids": best_focus_ids,
            "candidate_act_types": matched_types_in_order,
            "is_completion": bool(best_act.get("completion_act", False)) and completion_state == "ready",
        }

    def _resolve_focus_ids(self, planner: Dict[str, Any], status_groups: Dict[str, List[str]]) -> List[str]:
        focus = planner.get("focus", {}) if isinstance(planner.get("focus", {}), dict) else {}
        source = str(focus.get("source") or "none")
        limit = int(focus.get("limit", 2) or 2)

        if source == "matched_status":
            statuses = focus.get("statuses", [])
            for status in self._normalize_scalar_list(statuses):
                ids = status_groups.get(status, [])
                if ids:
                    return ids[:limit]
            return []
        if source in status_groups:
            return status_groups.get(source, [])[:limit]
        if source == "all_open":
            return (status_groups.get("conflict", []) + status_groups.get("ambiguous", []) + status_groups.get("unfilled", []))[:limit]
        if source == "all_slots":
            return status_groups.get("all", [])[:limit]
        return []

    def _build_status_groups(self, interaction_ir: Dict[str, Any], slot_update_result: Dict[str, Any]) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {
            "unfilled": [str(x) for x in slot_update_result.get("unfilled_slot_ids", []) if x is not None],
            "ambiguous": [str(x) for x in slot_update_result.get("ambiguous_slot_ids", []) if x is not None],
            "conflict": [str(x) for x in slot_update_result.get("conflict_slot_ids", []) if x is not None],
            "partial": [],
            "filled": [],
            "frozen": [],
            "all": [],
        }
        for slot in interaction_ir.get("slots", []):
            if not isinstance(slot, dict) or not slot.get("slot_id"):
                continue
            slot_id = str(slot.get("slot_id"))
            groups["all"].append(slot_id)
            status = str(slot.get("status") or "")
            if status in groups:
                groups[status].append(slot_id)
        return groups

    def _normalize_id_list(self, values: Any, id_field: str) -> List[str]:
        out: List[str] = []
        if not isinstance(values, list):
            return out
        for item in values:
            if isinstance(item, dict):
                value = item.get(id_field) or item.get("id") or item.get("value") or item.get("name")
            else:
                value = item
            if value is None:
                continue
            value_str = str(value).strip()
            if value_str and value_str not in out:
                out.append(value_str)
        return out

    def _normalize_scalar_list(self, values: Any) -> List[str]:
        out: List[str] = []
        if not isinstance(values, list):
            return out
        for item in values:
            if item is None:
                continue
            value_str = str(item).strip()
            if value_str and value_str not in out:
                out.append(value_str)
        return out

    def _extract_id(self, item: Any, id_field: str) -> str:
        if isinstance(item, dict):
            value = item.get(id_field) or item.get("id") or item.get("value") or item.get("name")
            return str(value).strip() if value is not None else ""
        return str(item).strip() if item is not None else ""
