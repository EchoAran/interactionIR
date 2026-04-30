from __future__ import annotations

import ast
import uuid
from typing import Any, Dict, List, Optional


class SlotsUpdater:
    def update(self, interaction_ir: Dict[str, Any], parse_result: Dict[str, Any], domain_package: Dict[str, Any]) -> Dict[str, Any]:
        slot_blueprints = [bp for bp in domain_package.get("slot_blueprint_catalog", []) if isinstance(bp, dict)]
        blueprints_by_key = {str(bp.get("slot_key")): bp for bp in slot_blueprints if bp.get("slot_key")}
        slots = interaction_ir.setdefault("slots", [])
        slots_by_key = {str(s.get("slot_key")): s for s in slots if isinstance(s, dict) and s.get("slot_key")}

        turn_id = self._next_turn_id(interaction_ir)
        checkpoint_before = str(interaction_ir.get("current_checkpoint") or "")
        slot_updates: List[Dict[str, Any]] = []

        for resolved in parse_result.get("resolved_slot_values", []):
            if not isinstance(resolved, dict):
                continue
            slot_key = str(resolved.get("slot_key") or "")
            if not slot_key or slot_key not in blueprints_by_key:
                continue
            slot = slots_by_key.get(slot_key)
            if slot is None:
                slot = self._create_slot_from_blueprint(blueprints_by_key[slot_key], domain_package)
                slots.append(slot)
                slots_by_key[slot_key] = slot
                slot_updates.append({
                    "slot_id": slot["slot_id"],
                    "operation": "create",
                    "old_value": None,
                    "new_value": slot.get("value"),
                })

            update_rule = blueprints_by_key[slot_key].get("update_rule", {}) if isinstance(blueprints_by_key[slot_key].get("update_rule", {}), dict) else {}
            if str(slot.get("status") or "") == "frozen" and not update_rule.get("allow_direct_overwrite_when_frozen", False):
                continue

            old_value = slot.get("value")
            new_value = resolved.get("value")
            slot["value"] = new_value
            slot["status"] = "filled" if not self._is_empty_value(new_value) else "unfilled"
            slot["confidence"] = max(0.0, min(1.0, float(resolved.get("confidence", 0.9) or 0.9)))
            slot["candidates"] = []
            source_turn_ids = slot.setdefault("source_turn_ids", [])
            if turn_id not in source_turn_ids:
                source_turn_ids.append(turn_id)
            slot_updates.append({
                "slot_id": slot.get("slot_id"),
                "operation": "resolve_conflict",
                "old_value": old_value,
                "new_value": slot.get("value"),
            })

        for candidate in parse_result.get("candidate_slot_values", []):
            if not isinstance(candidate, dict):
                continue
            slot_key = str(candidate.get("slot_key") or "")
            if not slot_key or slot_key not in blueprints_by_key:
                continue

            slot = slots_by_key.get(slot_key)
            if slot is None:
                slot = self._create_slot_from_blueprint(blueprints_by_key[slot_key], domain_package)
                slots.append(slot)
                slots_by_key[slot_key] = slot
                slot_updates.append({
                    "slot_id": slot["slot_id"],
                    "operation": "create",
                    "old_value": None,
                    "new_value": slot.get("value"),
                })

            updates = self._apply_candidate(slot, blueprints_by_key[slot_key], candidate, turn_id)
            for update in updates:
                slot_updates.append(update)

        checkpoint_after = self._recalculate_checkpoint(interaction_ir, domain_package)
        self._apply_checkpoint_freeze_rules(interaction_ir, domain_package)

        unfilled_slot_ids, ambiguous_slot_ids, conflict_slot_ids = self._collect_slot_state_groups(interaction_ir)

        return {
            "slot_updates": slot_updates,
            "unfilled_slot_ids": unfilled_slot_ids,
            "ambiguous_slot_ids": ambiguous_slot_ids,
            "conflict_slot_ids": conflict_slot_ids,
            "checkpoint_before": checkpoint_before,
            "checkpoint_after": checkpoint_after,
        }

    def _create_slot_from_blueprint(self, blueprint: Dict[str, Any], domain_package: Dict[str, Any]) -> Dict[str, Any]:
        slot_key = str(blueprint.get("slot_key"))
        title = str(blueprint.get("title") or slot_key)
        value_type = str(blueprint.get("value_type") or "text")
        raw_status_enum = blueprint.get("status_enum", None)
        if raw_status_enum is None:
            raw_status_enum = domain_package.get("slot_status_enum", [])
        status_enum = [str(x) for x in raw_status_enum if x] if isinstance(raw_status_enum, list) else []
        initial_status = "unfilled" if "unfilled" in status_enum else (status_enum[0] if status_enum else "unfilled")
        return {
            "slot_id": f"slot_{slot_key}_{uuid.uuid4().hex[:8]}",
            "slot_key": slot_key,
            "title": title,
            "type": value_type,
            "status": initial_status,
            "value": self._empty_value(value_type),
            "confidence": 0.0,
            "source_turn_ids": [],
            "candidates": [],
        }

    def _apply_candidate(
        self,
        slot: Dict[str, Any],
        blueprint: Dict[str, Any],
        candidate: Dict[str, Any],
        turn_id: str,
    ) -> List[Dict[str, Any]]:
        updates: List[Dict[str, Any]] = []
        update_rule = blueprint.get("update_rule", {}) if isinstance(blueprint.get("update_rule", {}), dict) else {}
        if str(slot.get("status") or "") == "frozen" and not update_rule.get("allow_direct_overwrite_when_frozen", False):
            return updates

        new_value = candidate.get("value")
        new_confidence = float(candidate.get("confidence", 0.0) or 0.0)
        old_value = slot.get("value")
        old_status = str(slot.get("status") or "")
        operation = "update"

        if self._is_empty_value(old_value):
            slot["value"] = new_value
            slot["status"] = "filled" if not self._is_empty_value(new_value) else "unfilled"
            operation = "fill"
            slot["candidates"] = []
        elif old_value == new_value:
            pass
        else:
            if update_rule.get("must_mark_conflict", True):
                slot["status"] = "conflict"
                operation = "mark_conflict"
                candidate_added = self._add_candidate(slot, new_value, new_confidence, turn_id)
                if old_status != "conflict":
                    updates.append({
                        "slot_id": slot.get("slot_id"),
                        "operation": operation,
                        "old_value": old_value,
                        "new_value": old_value,
                    })
                if candidate_added:
                    updates.append({
                        "slot_id": slot.get("slot_id"),
                        "operation": "add_candidate",
                        "old_value": None,
                        "new_value": candidate_added,
                    })
                operation = "noop"
            else:
                slot["value"] = new_value
                slot["status"] = "filled"
                operation = "update"
                slot["candidates"] = []

        slot["confidence"] = max(0.0, min(1.0, new_confidence))
        source_turn_ids = slot.setdefault("source_turn_ids", [])
        if turn_id not in source_turn_ids:
            source_turn_ids.append(turn_id)

        if operation in {"fill", "update"} and (old_value != slot.get("value") or old_status != slot.get("status")):
            updates.append({
                "slot_id": slot.get("slot_id"),
                "operation": operation,
                "old_value": old_value,
                "new_value": slot.get("value"),
            })
        return updates

    def _add_candidate(self, slot: Dict[str, Any], value: Any, confidence: float, turn_id: str) -> Optional[Dict[str, Any]]:
        if value is None or value == "" or value == [] or value == {}:
            return None
        candidates = slot.setdefault("candidates", [])
        if not isinstance(candidates, list):
            candidates = []
            slot["candidates"] = candidates
        for item in candidates:
            if isinstance(item, dict) and item.get("value") == value:
                return None
        candidate = {
            "value": value,
            "turn_id": str(turn_id),
            "confidence": max(0.0, min(1.0, float(confidence))),
        }
        candidates.append(candidate)
        return candidate

    def _recalculate_checkpoint(self, interaction_ir: Dict[str, Any], domain_package: Dict[str, Any]) -> str:
        checkpoints = [cp for cp in domain_package.get("checkpoint_catalog", []) if isinstance(cp, dict)]
        slots_by_key = {str(s.get("slot_key")): s for s in interaction_ir.get("slots", []) if isinstance(s, dict)}
        reached = str(interaction_ir.get("current_checkpoint") or "")

        for checkpoint in checkpoints:
            if self._conditions_satisfied(checkpoint.get("entry_conditions", []), slots_by_key):
                reached = str(checkpoint.get("checkpoint_id") or reached)
            else:
                break
        interaction_ir["current_checkpoint"] = reached
        return reached

    def _apply_checkpoint_freeze_rules(self, interaction_ir: Dict[str, Any], domain_package: Dict[str, Any]) -> None:
        current_checkpoint = str(interaction_ir.get("current_checkpoint") or "")
        freeze_keys: List[str] = []
        for checkpoint in domain_package.get("checkpoint_catalog", []):
            if isinstance(checkpoint, dict) and str(checkpoint.get("checkpoint_id") or "") == current_checkpoint:
                freeze_keys = [str(x) for x in checkpoint.get("freeze_slot_keys", []) if x]
                break
        for slot in interaction_ir.get("slots", []):
            if not isinstance(slot, dict):
                continue
            if str(slot.get("slot_key") or "") in freeze_keys:
                if str(slot.get("status") or "") == "filled":
                    slot["status"] = "frozen"

    def _conditions_satisfied(self, conditions: List[Any], slots_by_key: Dict[str, Dict[str, Any]]) -> bool:
        if not conditions:
            return True
        for condition in conditions:
            if not isinstance(condition, str):
                return False
            if not self._evaluate_condition(condition, slots_by_key):
                return False
        return True

    def _evaluate_condition(self, condition: str, slots_by_key: Dict[str, Dict[str, Any]]) -> bool:
        expr = condition.strip()
        if ".status in " in expr:
            left, right = expr.split(".status in ", 1)
            slot = slots_by_key.get(left.strip())
            if slot is None:
                return False
            allowed = ast.literal_eval(right.strip())
            return str(slot.get("status")) in allowed
        if ".status == " in expr:
            left, right = expr.split(".status == ", 1)
            slot = slots_by_key.get(left.strip())
            if slot is None:
                return False
            expected = ast.literal_eval(right.strip())
            return str(slot.get("status")) == expected
        if ".status != " in expr:
            left, right = expr.split(".status != ", 1)
            slot = slots_by_key.get(left.strip())
            if slot is None:
                return False
            expected = ast.literal_eval(right.strip())
            return str(slot.get("status")) != expected
        return False

    def _collect_slot_state_groups(self, interaction_ir: Dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
        unfilled: List[str] = []
        ambiguous: List[str] = []
        conflict: List[str] = []
        for slot in interaction_ir.get("slots", []):
            if not isinstance(slot, dict):
                continue
            slot_id = slot.get("slot_id")
            if not slot_id:
                continue
            status = str(slot.get("status") or "")
            if status in {"unfilled", "partial"}:
                unfilled.append(str(slot_id))
            elif status == "ambiguous":
                ambiguous.append(str(slot_id))
            elif status == "conflict":
                conflict.append(str(slot_id))
        return unfilled, ambiguous, conflict

    def _empty_value(self, value_type: str) -> Any:
        mapping = {
            "string": "",
            "text": "",
            "number": None,
            "boolean": None,
            "enum": None,
            "array": [],
            "object": {},
        }
        return mapping.get(value_type, None)

    def _is_empty_value(self, value: Any) -> bool:
        return value in (None, "", []) or value == {}

    def _next_turn_id(self, interaction_ir: Dict[str, Any]) -> str:
        history = interaction_ir.get("history", [])
        return f"turn_{len(history) + 1}"
