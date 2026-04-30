from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from llm_client import OpenAICompatibleLLMClient, build_client


class ParserChecker:
    def __init__(self, dotenv_path: Optional[str] = None, client: Optional[OpenAICompatibleLLMClient] = None) -> None:
        self.client = client or build_client(dotenv_path)

    def parse(self, user_input: str, interaction_ir: Dict[str, Any], domain_package: Dict[str, Any]) -> Dict[str, Any]:
        slots = [s for s in interaction_ir.get("slots", []) if isinstance(s, dict)]
        slot_summaries: List[Dict[str, Any]] = [
            {
                "slot_id": s.get("slot_id"),
                "slot_key": s.get("slot_key"),
                "title": s.get("title"),
                "status": s.get("status"),
                "value": s.get("value"),
                "frozen": s.get("frozen", False),
            }
            for s in slots
        ]
        parser_instruction = self._parser_instruction(domain_package)
        allowed_intentions = self._allowed_intentions(domain_package)
        allowed_slot_keys = self._allowed_slot_keys(domain_package)
        slot_blueprints = [bp for bp in domain_package.get("slot_blueprint_catalog", []) if isinstance(bp, dict)]

        raw = self._primary_parse(
            user_input=user_input,
            interaction_ir=interaction_ir,
            slot_summaries=slot_summaries,
            domain_package=domain_package,
            parser_instruction=parser_instruction,
        )
        result = self._normalize_result(raw, allowed_intentions, allowed_slot_keys)

        if self._needs_slot_extraction_fallback(result):
            fallback = self._fallback_extract_slot_values(user_input, slot_summaries, slot_blueprints)
            print(f"[DEBUG] Fallback triggered, fallback result: {json.dumps(fallback, ensure_ascii=False)[:500]}")  # 调试输出
            result = self._merge_fallback(result, fallback, allowed_intentions)

        if not result.get("parsed_intentions") and result.get("candidate_slot_values"):
            if "answer_slot" in allowed_intentions:
                result["parsed_intentions"] = ["answer_slot"]

        return result

    def _primary_parse(
        self,
        user_input: str,
        interaction_ir: Dict[str, Any],
        slot_summaries: List[Dict[str, Any]],
        domain_package: Dict[str, Any],
        parser_instruction: str,
    ) -> Dict[str, Any]:
        allowed_slot_keys = self._allowed_slot_keys(domain_package)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Parser/Checker in an interview controller. Return one JSON object only.\n"
                    "Goals:\n"
                    "1. Identify parsed_intentions using intention_catalog whenever possible.\n"
                    "2. Identify target_slot_keys that are directly touched by the user input.\n"
                    "3. candidate_slot_values must be conservative and directly supported by the user input. Provide it as a list of objects, e.g., [{\"slot_key\": \"...\", \"value\": \"...\", \"confidence\": 0.9}].\n"
                    "4. Do not invent missing details.\n"
                    f"5. Valid slot_keys are: {allowed_slot_keys}\n"
                    f"Additional parser guidance: {parser_instruction}\n"
                    "Output JSON keys: parsed_intentions, target_slot_keys, candidate_slot_values, notes"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "current_checkpoint": interaction_ir.get("current_checkpoint"),
                        "current_slots": slot_summaries,
                        "intention_catalog": domain_package.get("intention_catalog", []),
                        "slot_blueprint_catalog": domain_package.get("slot_blueprint_catalog", []),
                        "checkpoint_catalog": domain_package.get("checkpoint_catalog", []),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        raw = self.client.chat_json(messages, max_tokens=4096)
        print(f"[DEBUG] _primary_parse raw LLM output: {json.dumps(raw, ensure_ascii=False)[:500]}")  # 调试输出
        return raw

    def _fallback_extract_slot_values(
        self,
        user_input: str,
        slot_summaries: List[Dict[str, Any]],
        slot_blueprints: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a conservative slot extractor. Return one JSON object only.\n"
                    "Task: map the user input to one or more slot values based ONLY on direct evidence in the text.\n"
                    "Rules:\n"
                    "1. Only extract slots that are explicitly or strongly stated in the text.\n"
                    "2. Preserve the user's wording as much as possible.\n"
                    "3. For array slots, return a JSON array. For text slots, return a string.\n"
                    "4. If nothing can be safely extracted for a slot, do not output that slot.\n"
                    "5. candidate_slot_values MUST be a list of objects, e.g., [{\"slot_key\": \"...\", \"value\": \"...\", \"confidence\": 0.9}].\n"
                    "Output JSON keys: candidate_slot_values, notes"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_input": user_input,
                        "current_slots": slot_summaries,
                        "slot_blueprints": slot_blueprints,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        raw = self.client.chat_json(messages, max_tokens=4096)
        normalized: Dict[str, Any] = {"candidate_slot_values": [], "notes": []}
        raw_candidates = raw.get("candidate_slot_values", [])
        print(f"[DEBUG] _fallback_extract_slot_values raw LLM output: {json.dumps(raw, ensure_ascii=False)[:500]}")  # 调试输出
        if isinstance(raw_candidates, dict):
            for k, v in raw_candidates.items():
                slot_key = str(k).strip()
                if not slot_key:
                    continue
                normalized["candidate_slot_values"].append(
                    {
                        "slot_key": slot_key,
                        "value": v,
                        "confidence": 0.8,
                    }
                )
        elif isinstance(raw_candidates, list):
            for item in raw_candidates:
                if not isinstance(item, dict):
                    continue
                slot_key = self._extract_scalar(item.get("slot_key"), ["slot_key", "id", "value", "name", "key"])
                if not slot_key:
                    slot_key = self._extract_scalar(item.get("slot"), ["slot_key", "id", "value", "name", "key"])
                if not slot_key:
                    continue
                normalized["candidate_slot_values"].append(
                    {
                        "slot_key": slot_key,
                        "value": item.get("value"),
                        "confidence": self._safe_confidence(item.get("confidence", 0.7)),
                    }
                )
        raw_notes = raw.get("notes", [])
        if isinstance(raw_notes, list):
            for item in raw_notes:
                value = self._extract_scalar(item, ["value", "name", "text", "description"])
                if value:
                    normalized["notes"].append(value)
        return normalized

    def _merge_fallback(self, result: Dict[str, Any], fallback: Dict[str, Any], allowed_intentions: List[str]) -> Dict[str, Any]:
        existing_keys = {str(x.get("slot_key")) for x in result.get("candidate_slot_values", []) if isinstance(x, dict) and x.get("slot_key")}
        for item in fallback.get("candidate_slot_values", []):
            if not isinstance(item, dict):
                continue
            slot_key = str(item.get("slot_key") or "")
            if not slot_key or slot_key in existing_keys:
                continue
            result.setdefault("candidate_slot_values", []).append(item)
            existing_keys.add(slot_key)
            if slot_key not in result.setdefault("target_slot_keys", []):
                result["target_slot_keys"].append(slot_key)

        for note in fallback.get("notes", []):
            if isinstance(note, str) and note not in result.setdefault("notes", []):
                result["notes"].append(note)

        if result.get("candidate_slot_values") and not result.get("parsed_intentions") and "answer_slot" in allowed_intentions:
            result["parsed_intentions"] = ["answer_slot"]
        return result

    def _needs_slot_extraction_fallback(self, result: Dict[str, Any]) -> bool:
        return not bool(result.get("candidate_slot_values"))

    def _normalize_result(
        self,
        raw: Dict[str, Any],
        allowed_intentions: List[str],
        allowed_slot_keys: List[str],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        parsed_intentions: List[str] = []
        for item in raw.get("parsed_intentions", []) if isinstance(raw.get("parsed_intentions", []), list) else []:
            value = self._extract_scalar(item, ["intention_type", "id", "value", "name", "type"])
            if value and value in allowed_intentions and value not in parsed_intentions:
                parsed_intentions.append(value)

        target_slot_keys: List[str] = []
        for item in raw.get("target_slot_keys", []) if isinstance(raw.get("target_slot_keys", []), list) else []:
            value = self._extract_scalar(item, ["slot_key", "id", "value", "name", "key"])
            if value and value in allowed_slot_keys and value not in target_slot_keys:
                target_slot_keys.append(value)

        candidate_slot_values: List[Dict[str, Any]] = []
        raw_candidates = raw.get("candidate_slot_values", [])
        if isinstance(raw_candidates, dict):
            for k, v in raw_candidates.items():
                slot_key = str(k).strip()
                if not slot_key or slot_key not in allowed_slot_keys:
                    continue
                normalized = {
                    "slot_key": slot_key,
                    "value": v,
                    "confidence": 0.8,
                }
                candidate_slot_values.append(normalized)
                if slot_key not in target_slot_keys:
                    target_slot_keys.append(slot_key)
        elif isinstance(raw_candidates, list):
            for item in raw_candidates:
                if not isinstance(item, dict):
                    continue
                slot_key = self._extract_scalar(item.get("slot_key"), ["slot_key", "id", "value", "name", "key"])
                if not slot_key:
                    slot_key = self._extract_scalar(item.get("slot"), ["slot_key", "id", "value", "name", "key"])
                if not slot_key or slot_key not in allowed_slot_keys:
                    continue
                normalized = {
                    "slot_key": slot_key,
                    "value": item.get("value"),
                    "confidence": self._safe_confidence(item.get("confidence", 0.8)),
                }
                candidate_slot_values.append(normalized)
                if slot_key not in target_slot_keys:
                    target_slot_keys.append(slot_key)

        notes: List[str] = []
        raw_notes = raw.get("notes", [])
        if isinstance(raw_notes, list):
            for item in raw_notes:
                value = self._extract_scalar(item, ["value", "name", "text", "description"])
                if value:
                    notes.append(value)

        result["parsed_intentions"] = parsed_intentions
        result["target_slot_keys"] = target_slot_keys
        result["candidate_slot_values"] = candidate_slot_values
        result["notes"] = notes
        return result

    def _allowed_intentions(self, domain_package: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for item in domain_package.get("intention_catalog", []):
            if not isinstance(item, dict):
                continue
            value = self._extract_scalar(item.get("intention_type"), ["intention_type", "id", "value", "name", "type"])
            if value and value not in out:
                out.append(value)
        return out

    def _allowed_slot_keys(self, domain_package: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for item in domain_package.get("slot_blueprint_catalog", []):
            if not isinstance(item, dict):
                continue
            value = self._extract_scalar(item.get("slot_key"), ["slot_key", "id", "value", "name", "key"])
            if value and value not in out:
                out.append(value)
        return out

    def _parser_instruction(self, domain_package: Dict[str, Any]) -> str:
        parser_guidance = domain_package.get("parser_guidance", {})
        if isinstance(parser_guidance, dict) and parser_guidance.get("instruction"):
            return str(parser_guidance.get("instruction"))
        return "Prefer conservative parsing and stay aligned with the package catalogs."

    def _extract_scalar(self, value: Any, candidate_keys: List[str]) -> str:
        if isinstance(value, dict):
            for key in candidate_keys:
                inner = value.get(key)
                if isinstance(inner, (str, int, float, bool)):
                    text = str(inner).strip()
                    if text:
                        return text
            return ""
        if isinstance(value, (str, int, float, bool)):
            text = str(value).strip()
            return text
        return ""

    def _safe_confidence(self, value: Any) -> float:
        try:
            num = float(value)
        except Exception:
            num = 0.0
        return max(0.0, min(1.0, num))
