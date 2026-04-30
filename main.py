from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from Creator import Creator, DomainPackageRecord, load_json, save_json_atomic, scan_domain_packages
from Parser_Checker import ParserChecker
from Renderer import Renderer
from acts_Planner import ActsPlanner
from history_Writer import HistoryWriter
from policies_Evaluator import PoliciesEvaluator
from slots_Updater import SlotsUpdater
from llm_client import LLMClientError,build_client
from protocol import ROUTE_SKIP_ACTUATOR

BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = str(BASE_DIR / ".env")
DOMAIN_DIR = BASE_DIR / "domain_packages"
PACKAGE_SCHEMA_PATH = BASE_DIR / "packages_schema.json"
INTERACTION_SCHEMA_PATH = BASE_DIR / "interactionIR_schema.json"
INTERACTION_RUNTIME_PATH = BASE_DIR / "interactionIR.runtime.json"


def resolve_domain_package(interaction_ir: Dict[str, Any], domain_dir: Path, package_schema_path: Path) -> DomainPackageRecord:
    meta = interaction_ir.get("meta", {}) if isinstance(interaction_ir.get("meta", {}), dict) else {}
    domain_id = str(meta.get("domain_id") or "")
    version = str(meta.get("domain_version") or "")
    for record in scan_domain_packages(domain_dir, package_schema_path):
        if record.domain_id == domain_id and record.version == version:
            return record
    raise FileNotFoundError("Cannot resolve domain package from interactionIR meta")


def run_turn(user_input: str, interaction_ir: Dict[str, Any], domain_package: Dict[str, Any]) -> str:
    parser_checker = ParserChecker(dotenv_path=DOTENV_PATH)
    slots_updater = SlotsUpdater()
    policies_evaluator = PoliciesEvaluator()
    acts_planner = ActsPlanner()
    renderer = Renderer()
    history_writer = HistoryWriter()

    parse_result = parser_checker.parse(user_input, interaction_ir, domain_package)
    print(f"[DEBUG] parse_result: {parse_result}")  # 调试输出
    route = str(parse_result.get("route") or "")

    if not parse_result.get("need_invoke_actuator", True) or route == ROUTE_SKIP_ACTUATOR:
        slot_update_result = {
            "slot_updates": [],
            "unfilled_slot_ids": [],
            "ambiguous_slot_ids": [],
            "conflict_slot_ids": [],
            "checkpoint_before": interaction_ir.get("current_checkpoint"),
            "checkpoint_after": interaction_ir.get("current_checkpoint"),
        }
        policy_result = {"selected_policy_ids": [], "policy_constraints": {}, "completion_state": "not_ready"}
        act_result = {"selected_act_type": None, "focus_slot_ids": [], "candidate_act_types": [], "is_completion": False}
        text = "当前输入不进入访谈执行链。"
        history_writer.append(interaction_ir, user_input, parse_result, slot_update_result, policy_result, act_result)
        return text

    slot_update_result = slots_updater.update(interaction_ir, parse_result, domain_package)
    print(f"[DEBUG] slot_update_result: {slot_update_result}")  # 调试输出
    policy_result = policies_evaluator.evaluate(interaction_ir, parse_result, slot_update_result, domain_package)
    act_result = acts_planner.plan(interaction_ir, parse_result, slot_update_result, policy_result, domain_package)
    rendered_context = renderer.render(interaction_ir, parse_result, slot_update_result, policy_result, act_result, domain_package)
    history_writer.append(interaction_ir, user_input, parse_result, slot_update_result, policy_result, act_result)
    return rendered_context


def ensure_runtime_for_first_turn(user_input: str) -> tuple[Dict[str, Any], DomainPackageRecord]:
    creator = Creator(
        domain_dir=DOMAIN_DIR,
        interactionir_schema_path=INTERACTION_SCHEMA_PATH,
        package_schema_path=PACKAGE_SCHEMA_PATH,
        dotenv_path=DOTENV_PATH,
    )
    interaction_ir, selected_pkg = creator.create(user_input)
    save_json_atomic(INTERACTION_RUNTIME_PATH, interaction_ir)
    return interaction_ir, selected_pkg


def main() -> int:
    print("interactionIR runtime started. 输入 exit 或 quit 退出。")
    while True:
        try:
            user_input = input("user> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            return 0

        try:
            if not INTERACTION_RUNTIME_PATH.exists():
                interaction_ir, domain_package_record = ensure_runtime_for_first_turn(user_input)
            else:
                interaction_ir = load_json(INTERACTION_RUNTIME_PATH)
                domain_package_record = resolve_domain_package(interaction_ir, DOMAIN_DIR, PACKAGE_SCHEMA_PATH)

            rendered_context = run_turn(user_input, interaction_ir, domain_package_record.data)
            save_json_atomic(INTERACTION_RUNTIME_PATH, interaction_ir)
            
            print(rendered_context)
            client = build_client(DOTENV_PATH)
            messages = [
                {"role": "system", "content": "你是一个外部执行代理。严格遵守执行上下文的指示。"},
                {"role": "user", "content": rendered_context}
            ]
            agent_response = client.chat(messages)
            print(f"agent> {agent_response}")
        except (ValueError, FileNotFoundError, LLMClientError) as exc:
            print(f"[ERROR] {exc}")
        except Exception as exc:  # pragma: no cover
            print(f"[ERROR] Unexpected failure: {exc}")
    

if __name__ == "__main__":
    raise SystemExit(main())
