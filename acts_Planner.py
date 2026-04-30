from __future__ import annotations

from typing import Any, Dict, List, Tuple


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

        preferred_act_types: List[str] = []
        for checkpoint in domain_package.get("checkpoint_catalog", []):
            if isinstance(checkpoint, dict) and str(checkpoint.get("checkpoint_id") or "") == current_checkpoint:
                preferred_act_types = self._normalize_id_list(checkpoint.get("preferred_act_types", []), "act_type")
                break

        candidates: List[Tuple[float, Dict[str, Any], List[str]]] = []
        for act in domain_package.get("act_catalog", []):
            act_type = self._extract_id(act, "act_type")
            if not isinstance(act, dict) or not act_type:
                continue
            planner = act.get("planner", {}) if isinstance(act.get("planner", {}), dict) else {}
            when = planner.get("when", {}) if isinstance(planner.get("when", {}), dict) else {}
            if not self._when_matches(when, intentions, current_checkpoint, completion_state, status_groups):
                continue
            focus_slot_ids = self._resolve_focus_ids(planner, status_groups)
            score = float(planner.get("priority", 0) or 0)
            if act_type in preferred_act_types:
                score += 1000.0
            candidates.append((score, act, focus_slot_ids))

        if not candidates:
            by_type = {
                self._extract_id(a, "act_type"): a
                for a in domain_package.get("act_catalog", [])
                if isinstance(a, dict) and self._extract_id(a, "act_type")
            }
            for act_type in preferred_act_types:
                if act_type in by_type:
                    focus_slot_ids = self._resolve_focus_ids(by_type[act_type].get("planner", {}), status_groups)
                    return {
                        "selected_act_type": act_type,
                        "focus_slot_ids": focus_slot_ids,
                        "candidate_act_types": [act_type],
                        "is_completion": completion_state == "ready" and bool(by_type[act_type].get("completion_act", False)),
                    }
            first_act = next((a for a in domain_package.get("act_catalog", []) if isinstance(a, dict) and self._extract_id(a, "act_type")), None)
            if first_act is None:
                return {"selected_act_type": None, "focus_slot_ids": [], "candidate_act_types": [], "is_completion": False}
            first_act_type = self._extract_id(first_act, "act_type")
            return {
                "selected_act_type": first_act_type,
                "focus_slot_ids": self._resolve_focus_ids(first_act.get("planner", {}), status_groups),
                "candidate_act_types": [first_act_type],
                "is_completion": bool(first_act.get("completion_act", False)) and completion_state == "ready",
            }

        candidates.sort(key=lambda item: item[0], reverse=True)
        _, best_act, best_focus_ids = candidates[0]
        return {
            "selected_act_type": self._extract_id(best_act, "act_type"),
            "focus_slot_ids": best_focus_ids,
            "candidate_act_types": [self._extract_id(act, "act_type") for _, act, _ in candidates if self._extract_id(act, "act_type")],
            "is_completion": bool(best_act.get("completion_act", False)) and completion_state == "ready",
        }

    def _when_matches(
        self,
        when: Dict[str, Any],
        intentions: List[str],
        current_checkpoint: str,
        completion_state: str,
        status_groups: Dict[str, List[str]],
    ) -> bool:
        intentions_any = self._normalize_id_list(when.get("intentions_any", []), "intention_type")
        checkpoints_any = self._normalize_id_list(when.get("checkpoints_any", []), "checkpoint_id")
        completion_any = self._normalize_scalar_list(when.get("completion_state_any", []))
        status_any = self._normalize_scalar_list(when.get("slot_status_any", []))

        if intentions_any and not any(i in intentions_any for i in intentions):
            return False
        if checkpoints_any and current_checkpoint not in checkpoints_any:
            return False
        if completion_any and completion_state not in completion_any:
            return False
        if status_any and not any(status_groups.get(status) for status in status_any):
            return False
        return bool(intentions_any or checkpoints_any or completion_any or status_any)

    def _resolve_focus_ids(self, planner: Dict[str, Any], status_groups: Dict[str, List[str]]) -> List[str]:
        focus = planner.get("focus", {}) if isinstance(planner.get("focus", {}), dict) else {}
        source = str(focus.get("source") or "none")
        limit = int(focus.get("limit", 2) or 2)
        when = planner.get("when", {}) if isinstance(planner.get("when", {}), dict) else {}
        status_any = self._normalize_scalar_list(when.get("slot_status_any", []))

        if source == "matched_status":
            for status in status_any:
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
