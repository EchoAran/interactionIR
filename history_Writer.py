from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


class HistoryWriter:
    def append(
        self,
        interaction_ir: Dict[str, Any],
        user_input: str,
        parse_result: Dict[str, Any],
        slot_update_result: Dict[str, Any],
        policy_result: Dict[str, Any],
        act_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        history = interaction_ir.setdefault("history", [])
        turn_id = f"turn_{len(history) + 1}"
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        entry = {
            "turn_id": turn_id,
            "user_input": user_input,
            "parsed_intentions": parse_result.get("parsed_intentions", []),
            "slot_updates": slot_update_result.get("slot_updates", []),
            "selected_policy_ids": policy_result.get("selected_policy_ids", []),
            "selected_act_types": act_result.get("selected_act_types", []) or ([] if act_result.get("selected_act_type") is None else [act_result.get("selected_act_type")]),
            "selected_act_type": act_result.get("selected_act_type") or (act_result.get("selected_act_types", []) or [None])[0],
            "checkpoint_before": slot_update_result.get("checkpoint_before"),
            "checkpoint_after": slot_update_result.get("checkpoint_after"),
            "timestamp": timestamp,
        }
        history.append(entry)
        meta = interaction_ir.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["updated_at"] = timestamp
        interaction_ir["active_intentions"] = parse_result.get("parsed_intentions", [])
        return entry
