from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from llm_client import build_client

try:
    from jsonschema import validate  # type: ignore
except Exception:  # pragma: no cover
    validate = None  # type: ignore


@dataclass
class DomainPackageRecord:
    path: Path
    data: Dict[str, Any]

    @property
    def domain_id(self) -> str:
        return str(self.data.get("domain_id", ""))

    @property
    def version(self) -> str:
        return str(self.data.get("version", ""))


def load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def save_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _validate_json(data: Dict[str, Any], schema_path: Optional[Path]) -> None:
    if validate is None or schema_path is None or not schema_path.exists():
        return
    schema = load_json(schema_path)
    validate(instance=data, schema=schema)


def scan_domain_packages(domain_dir: Path, package_schema_path: Optional[Path] = None) -> List[DomainPackageRecord]:
    if not domain_dir.exists() or not domain_dir.is_dir():
        raise FileNotFoundError(f"Domain package directory not found: {domain_dir}")

    records: List[DomainPackageRecord] = []
    for path in sorted(domain_dir.rglob("*.json")):
        name = path.name.lower()
        if name.endswith("schema.json") or name.endswith("_schema.json"):
            continue
        try:
            data = load_json(path)
            required = {
                "domain_id",
                "version",
                "slot_blueprint_catalog",
                "policy_catalog",
                "act_catalog",
                "checkpoint_catalog",
                "intention_catalog",
            }
            if not required.issubset(data.keys()):
                continue
            _validate_json(data, package_schema_path)
            records.append(DomainPackageRecord(path=path, data=data))
        except Exception:
            continue

    if not records:
        raise ValueError(f"No valid domain packages found under {domain_dir}")
    return records


def summarize_domain_package(record: DomainPackageRecord) -> Dict[str, Any]:
    data = record.data
    return {
        "domain_id": record.domain_id,
        "version": record.version,
        "description": data.get("description", ""),
        "path": str(record.path),
        "slot_blueprints": [
            {
                "slot_key": bp.get("slot_key"),
                "title": bp.get("title"),
                "description": bp.get("description", ""),
            }
            for bp in data.get("slot_blueprint_catalog", [])
            if isinstance(bp, dict)
        ],
        "intention_types": [
            it.get("intention_type")
            for it in data.get("intention_catalog", [])
            if isinstance(it, dict)
        ],
        "checkpoint_labels": [
            cp.get("label") or cp.get("checkpoint_id")
            for cp in data.get("checkpoint_catalog", [])
            if isinstance(cp, dict)
        ],
    }


class Creator:
    def __init__(
        self,
        domain_dir: Path,
        interactionir_schema_path: Path,
        *,
        package_schema_path: Optional[Path] = None,
        dotenv_path: Optional[str] = None,
    ) -> None:
        self.domain_dir = domain_dir
        self.interactionir_schema_path = interactionir_schema_path
        self.package_schema_path = package_schema_path
        self.dotenv_path = dotenv_path
        self.client = build_client(dotenv_path)
        self.interactionir_schema = load_json(interactionir_schema_path)

    def create(self, initial_requirement: str) -> Tuple[Dict[str, Any], DomainPackageRecord]:
        packages = scan_domain_packages(self.domain_dir, self.package_schema_path)
        selected = self._choose_package(initial_requirement, packages)
        interaction_ir = self._build_empty_interaction_ir(selected)
        self._validate_interaction_ir(interaction_ir)
        return interaction_ir, selected

    def _choose_package(self, requirement: str, packages: List[DomainPackageRecord]) -> DomainPackageRecord:
        if len(packages) == 1:
            return packages[0]

        package_summaries = [summarize_domain_package(pkg) for pkg in packages]
        messages = [
            {
                "role": "system",
                "content": (
                    "You select the most suitable domain package for an initial user requirement. "
                    "Return exactly one JSON object with keys path, domain_id, version, reason. "
                    "Choose conservatively based on the package descriptions and slot blueprints."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"initial_requirement": requirement, "candidates": package_summaries},
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        result = self.client.chat_json(messages)
        chosen_path = str(result.get("path", "")).strip()
        chosen_domain_id = str(result.get("domain_id", "")).strip()
        chosen_version = str(result.get("version", "")).strip()

        for pkg in packages:
            if chosen_path and str(pkg.path) == chosen_path:
                return pkg
            if pkg.domain_id == chosen_domain_id and pkg.version == chosen_version:
                return pkg
        raise ValueError("LLM selected an unknown domain package")

    def _build_empty_interaction_ir(self, selected_pkg: DomainPackageRecord) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        meta = {
            "interaction_id": f"ir-{uuid.uuid4().hex[:12]}",
            "domain_id": selected_pkg.domain_id,
            "domain_version": selected_pkg.version,
            "created_at": now,
            "updated_at": now,
            "status": "active",
        }
        slots = [
            self._make_slot_instance(bp, selected_pkg.data)
            for bp in selected_pkg.data.get("slot_blueprint_catalog", [])
            if isinstance(bp, dict) and bool(bp.get("creation_rule", {}).get("create_at_init", True))
        ]

        checkpoint_catalog = [cp for cp in selected_pkg.data.get("checkpoint_catalog", []) if isinstance(cp, dict)]
        current_checkpoint = ""
        if checkpoint_catalog:
            current_checkpoint = str(checkpoint_catalog[0].get("checkpoint_id") or "")

        return {
            "meta": meta,
            "slots": slots,
            "current_checkpoint": current_checkpoint,
            "active_intentions": [],
            "history": [],
        }

    def _make_slot_instance(self, blueprint: Dict[str, Any], domain_package: Dict[str, Any]) -> Dict[str, Any]:
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
        }

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

    def _validate_interaction_ir(self, interaction_ir: Dict[str, Any]) -> None:
        if validate is None:
            return
        validate(instance=interaction_ir, schema=self.interactionir_schema)
