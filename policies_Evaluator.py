from __future__ import annotations

from typing import Any, Dict, List

from condition_eval import ConditionEvaluator


class PoliciesEvaluator:
    def evaluate(
        self,
        interaction_ir: Dict[str, Any],
        parse_result: Dict[str, Any],
        slot_update_result: Dict[str, Any],
        domain_package: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_checkpoint = str(interaction_ir.get("current_checkpoint") or "")
        active_intentions = [str(x) for x in parse_result.get("parsed_intentions", []) if x is not None]
        slot_statuses = [str(slot.get("status") or "") for slot in interaction_ir.get("slots", []) if isinstance(slot, dict)]
        completion_state = self._completion_state(slot_update_result)
        evaluator = ConditionEvaluator()
        ctx = {
            "checkpoint": current_checkpoint,
            "intentions": active_intentions,
            "slot_statuses": slot_statuses,
            "completion_state": completion_state,
        }

        preferred_policy_ids: List[str] = []
        for checkpoint in domain_package.get("checkpoint_catalog", []):
            if isinstance(checkpoint, dict) and str(checkpoint.get("checkpoint_id") or "") == current_checkpoint:
                preferred_policy_ids = self._normalize_id_list(checkpoint.get("preferred_policy_ids", []), "policy_id")
                break

        selected_policy_ids: List[str] = []
        for policy_id in preferred_policy_ids:
            if policy_id and policy_id not in selected_policy_ids:
                selected_policy_ids.append(policy_id)

        policy_catalog = [p for p in domain_package.get("policy_catalog", []) if isinstance(p, dict)]
        for policy in policy_catalog:
            trigger = policy.get("trigger", {}) if isinstance(policy.get("trigger", {}), dict) else {}
            conditions = trigger.get("conditions", [])
            if evaluator.evaluate_all(conditions, ctx):
                policy_id = self._extract_id(policy, "policy_id")
                if policy_id and policy_id not in selected_policy_ids:
                    selected_policy_ids.append(policy_id)

        policy_constraints: Dict[str, Any] = {}
        by_id = {
            self._extract_id(p, "policy_id"): p
            for p in policy_catalog
            if self._extract_id(p, "policy_id")
        }
        for policy_id in selected_policy_ids:
            policy = by_id.get(str(policy_id))
            if not policy:
                continue
            constraints = policy.get("constraints", {}) if isinstance(policy.get("constraints", {}), dict) else {}
            policy_constraints.update(constraints)

        return {
            "selected_policy_ids": selected_policy_ids,
            "policy_constraints": policy_constraints,
            "completion_state": completion_state,
        }

    def _completion_state(self, slot_update_result: Dict[str, Any]) -> str:
        if slot_update_result.get("unfilled_slot_ids") or slot_update_result.get("ambiguous_slot_ids") or slot_update_result.get("conflict_slot_ids"):
            return "not_ready"
        return "ready"

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

    def _extract_id(self, item: Any, id_field: str) -> str:
        if isinstance(item, dict):
            value = item.get(id_field) or item.get("id") or item.get("value") or item.get("name")
            return str(value).strip() if value is not None else ""
        return str(item).strip() if item is not None else ""
