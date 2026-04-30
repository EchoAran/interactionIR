from __future__ import annotations

from typing import Any, Dict, List


class Renderer:
    """Render package-driven external-agent context."""

    def render(
        self,
        interaction_ir: Dict[str, Any],
        parse_result: Dict[str, Any],
        slot_update_result: Dict[str, Any],
        policy_result: Dict[str, Any],
        act_result: Dict[str, Any],
        domain_package: Dict[str, Any],
    ) -> str:
        slots = [s for s in interaction_ir.get("slots", []) if isinstance(s, dict)]
        slot_by_id = {str(s.get("slot_id")): s for s in slots if s.get("slot_id")}
        slot_blueprints = {
            str(bp.get("slot_key")): bp
            for bp in domain_package.get("slot_blueprint_catalog", [])
            if isinstance(bp, dict) and bp.get("slot_key")
        }
        policy_by_id = {
            str(p.get("policy_id")): p
            for p in domain_package.get("policy_catalog", [])
            if isinstance(p, dict) and p.get("policy_id")
        }
        act_by_type = {
            str(a.get("act_type")): a
            for a in domain_package.get("act_catalog", [])
            if isinstance(a, dict) and a.get("act_type")
        }
        checkpoint_by_id = {
            str(c.get("checkpoint_id")): c
            for c in domain_package.get("checkpoint_catalog", [])
            if isinstance(c, dict) and c.get("checkpoint_id")
        }
        intention_by_type = {
            str(i.get("intention_type")): i
            for i in domain_package.get("intention_catalog", [])
            if isinstance(i, dict) and i.get("intention_type")
        }

        current_checkpoint = str(interaction_ir.get("current_checkpoint") or "")
        checkpoint_spec = checkpoint_by_id.get(current_checkpoint, {})
        selected_policy_ids = self._normalize_scalar_list(policy_result.get("selected_policy_ids", []))
        selected_act_type = str(act_result.get("selected_act_type") or "")
        selected_act_spec = act_by_type.get(selected_act_type, {})
        focus_slot_ids = self._normalize_scalar_list(act_result.get("focus_slot_ids", []))
        focus_slots = [slot_by_id[sid] for sid in focus_slot_ids if sid in slot_by_id]
        completion_state = str(policy_result.get("completion_state") or "not_ready")
        is_completion = bool(act_result.get("is_completion")) or completion_state == "ready"

        lines: List[str] = []
        lines.append("你现在扮演外部执行代理。以下是本轮必须遵守的执行上下文。")
        lines.append("")

        checkpoint_label = str(checkpoint_spec.get("label") or current_checkpoint or "当前阶段未命名")
        lines.append(f"当前阶段：{checkpoint_label}。")
        checkpoint_renderer = checkpoint_spec.get("renderer", {}) if isinstance(checkpoint_spec.get("renderer", {}), dict) else {}
        checkpoint_desc = self._first_text(checkpoint_renderer.get("description"), checkpoint_spec.get("description"))
        if checkpoint_desc:
            lines.append(checkpoint_desc)

        parsed_intentions = self._normalize_scalar_list(parse_result.get("parsed_intentions", []), id_keys=["intention_type", "id", "value", "name", "type"])
        intent_desc = self._join_nonempty([
            self._first_text(
                intention_by_type.get(intent, {}).get("renderer", {}).get("instruction") if isinstance(intention_by_type.get(intent, {}).get("renderer", {}), dict) else None,
                intention_by_type.get(intent, {}).get("description"),
            )
            for intent in parsed_intentions
        ])
        if intent_desc:
            lines.append(f"用户本轮情况：{intent_desc}")

        summary = self._state_summary(slots)
        lines.append(summary)

        act_instruction = self._first_text(
            selected_act_spec.get("renderer", {}).get("instruction") if isinstance(selected_act_spec.get("renderer", {}), dict) else None,
            selected_act_spec.get("description"),
        )

        if is_completion:
            completion_instruction = self._first_text(
                checkpoint_renderer.get("completion_instruction"),
                checkpoint_renderer.get("wrap_up_instruction"),
                act_instruction,
            )
            if completion_instruction:
                lines.append(f"本轮核心任务：{completion_instruction}")
            else:
                lines.append("本轮核心任务：请对当前访谈做收束，总结已确认信息，并向用户确认是否还需补充或修正。")
        elif act_instruction:
            lines.append(f"本轮核心任务：{act_instruction}")

        if focus_slots:
            lines.append("请优先处理以下焦点信息：")
            for slot in focus_slots:
                lines.append(self._focus_slot_line(slot, slot_blueprints.get(str(slot.get("slot_key") or ""), {})))

        policy_lines = self._policy_instruction_lines(selected_policy_ids, policy_by_id)
        if policy_lines:
            lines.append("执行约束：")
            lines.extend([f"- {line}" for line in policy_lines])

        output_hint = self._first_text(
            selected_act_spec.get("renderer", {}).get("output_hint") if isinstance(selected_act_spec.get("renderer", {}), dict) else None,
        )
        if output_hint:
            lines.append(f"输出要求：{output_hint}")
        else:
            lines.append("输出要求：直接面向用户开展下一轮交流，不要暴露内部状态名、策略名或动作名。")

        return "\n".join(line for line in lines if line is not None and line != "").strip()

    def _state_summary(self, slots: List[Dict[str, Any]]) -> str:
        counts = {"filled": 0, "partial": 0, "open": 0, "conflict": 0}
        for slot in slots:
            status = str(slot.get("status") or "")
            if status in {"filled", "frozen"}:
                counts["filled"] += 1
            elif status == "partial":
                counts["partial"] += 1
                counts["open"] += 1
            elif status == "conflict":
                counts["conflict"] += 1
                counts["open"] += 1
            else:
                counts["open"] += 1
        return (
            f"状态摘要：已明确 {counts['filled']} 个信息槽，部分明确 {counts['partial']} 个信息槽，"
            f"仍待处理 {counts['open']} 个信息槽，其中冲突 {counts['conflict']} 个。"
        )

    def _focus_slot_line(self, slot: Dict[str, Any], blueprint: Dict[str, Any]) -> str:
        title = str(slot.get("title") or slot.get("slot_key") or slot.get("slot_id"))
        status = str(slot.get("status") or "unknown")
        value = slot.get("value")
        renderer = blueprint.get("renderer", {}) if isinstance(blueprint.get("renderer", {}), dict) else {}
        missing_hint = self._first_text(renderer.get("missing_hint"), blueprint.get("description"))
        value_hint = self._first_text(renderer.get("value_hint"))
        line = f"- {title}，当前状态为 {status}。"
        if value not in (None, "", [], {}):
            line += f" 当前已有内容：{self._stringify_value(value)}。"
            if value_hint:
                line += f" {value_hint}"
        elif missing_hint:
            line += f" 需要补充：{missing_hint}"
        return line

    def _policy_instruction_lines(self, selected_policy_ids: List[str], policy_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
        lines: List[str] = []
        for policy_id in selected_policy_ids:
            policy = policy_by_id.get(policy_id)
            if not policy:
                continue
            renderer = policy.get("renderer", {}) if isinstance(policy.get("renderer", {}), dict) else {}
            base = self._first_text(renderer.get("instruction"), policy.get("description"))
            if base:
                lines.append(base)
            notes = renderer.get("notes") if isinstance(renderer.get("notes"), list) else []
            for note in notes:
                if isinstance(note, str) and note.strip():
                    lines.append(note.strip())
        deduped: List[str] = []
        for line in lines:
            if line not in deduped:
                deduped.append(line)
        return deduped

    def _normalize_scalar_list(self, values: Any, id_keys: List[str] | None = None) -> List[str]:
        out: List[str] = []
        keys = id_keys or ["id", "value", "name", "type"]
        if not isinstance(values, list):
            return out
        for item in values:
            value = ""
            if isinstance(item, dict):
                for key in keys:
                    inner = item.get(key)
                    if isinstance(inner, (str, int, float, bool)):
                        value = str(inner).strip()
                        if value:
                            break
            elif isinstance(item, (str, int, float, bool)):
                value = str(item).strip()
            if value and value not in out:
                out.append(value)
        return out

    def _first_text(self, *values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _join_nonempty(self, values: List[str]) -> str:
        cleaned = [v.strip() for v in values if isinstance(v, str) and v.strip()]
        return "；".join(cleaned)

    def _stringify_value(self, value: Any) -> str:
        if isinstance(value, list):
            return "，".join(str(v) for v in value)
        if isinstance(value, dict):
            return str(value)
        return str(value)
