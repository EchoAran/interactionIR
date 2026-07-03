import os
from typing import Any, Dict
from handoff_runtime.agent import Agent
from handoff_runtime.events import RuntimeEvent

from Creator import Creator, scan_domain_packages, save_json_atomic, load_json
from Parser_Checker import ParserChecker
from slots_Updater import SlotsUpdater
from policies_Evaluator import PoliciesEvaluator
from acts_Planner import ActsPlanner
from Renderer import Renderer
from history_Writer import HistoryWriter
from llm_client import build_client

class InteractionIRAgent(Agent):
    def __init__(self, config: dict = None):
        if config is None:
            config = {}
        self.domain_dir = config.get("domain_dir", "domain_packages")
        self.package_schema_path = config.get("package_schema_path", "packages_schema.json")
        self.interactionir_schema_path = config.get("interactionir_schema_path", "interactionIR_schema.json")
        self.dotenv_path = config.get("dotenv_path", ".env")
        self.runtime_path = config.get("runtime_path", "interactionIR.runtime.json")
        
        # Convert paths to pathlib.Path as expected by underlying components
        from pathlib import Path
        self.domain_dir = Path(self.domain_dir) if isinstance(self.domain_dir, str) else self.domain_dir
        self.package_schema_path = Path(self.package_schema_path) if isinstance(self.package_schema_path, str) else self.package_schema_path
        self.interactionir_schema_path = Path(self.interactionir_schema_path) if isinstance(self.interactionir_schema_path, str) else self.interactionir_schema_path
        self.runtime_path = Path(self.runtime_path) if isinstance(self.runtime_path, str) else self.runtime_path
        self.dotenv_path = str(self.dotenv_path) # ParserChecker expects string for dotenv_path

        
        self.parser_checker = ParserChecker(dotenv_path=self.dotenv_path)
        self.slots_updater = SlotsUpdater()
        self.policies_evaluator = PoliciesEvaluator()
        self.acts_planner = ActsPlanner()
        self.renderer = Renderer()
        self.history_writer = HistoryWriter()
        self.llm_client = build_client(self.dotenv_path)
        
    def _resolve_domain_package(self, interaction_ir: Dict[str, Any]) -> Dict[str, Any]:
        meta = interaction_ir.get("meta", {}) if isinstance(interaction_ir.get("meta", {}), dict) else {}
        domain_id = str(meta.get("domain_id") or "")
        version = str(meta.get("domain_version") or "")
        for record in scan_domain_packages(self.domain_dir, self.package_schema_path):
            if record.domain_id == domain_id and record.version == version:
                return record.data
        raise FileNotFoundError("Cannot resolve domain package from interactionIR meta")

    def on_enter(self, payload: Dict[str, Any], runtime_context: Dict[str, Any]) -> RuntimeEvent:
        # payload expected to contain "initial_user_need"
        initial_need = payload.get("initial_user_need", "")
        
        creator = Creator(
            domain_dir=self.domain_dir,
            interactionir_schema_path=self.interactionir_schema_path,
            package_schema_path=self.package_schema_path,
            dotenv_path=self.dotenv_path,
        )
        
        # Create initial state
        interaction_ir, selected_pkg = creator.create(initial_need)
        runtime_context["interaction_ir"] = interaction_ir
        runtime_context["domain_package"] = selected_pkg.data
        
        save_json_atomic(self.runtime_path, interaction_ir)
        
        # Run first turn using initial need
        return self._run_turn(initial_need, interaction_ir, selected_pkg.data, runtime_context)

    def on_message(self, user_message: str, runtime_context: Dict[str, Any]) -> RuntimeEvent:
        interaction_ir = runtime_context.get("interaction_ir")
        domain_package = runtime_context.get("domain_package")
        
        if not interaction_ir or not domain_package:
            return RuntimeEvent(type="error", content="Missing runtime state")
            
        return self._run_turn(user_message, interaction_ir, domain_package, runtime_context)
        
    def _run_turn(self, user_input: str, interaction_ir: Dict[str, Any], domain_package: Dict[str, Any], runtime_context: Dict[str, Any]) -> RuntimeEvent:
        parse_result = self.parser_checker.parse(user_input, interaction_ir, domain_package)
        route = str(parse_result.get("route") or "")
        
        # 显式处理结束访谈的意图
        parsed_intentions = parse_result.get("parsed_intentions", [])
        is_finish_intention = "finish_interview" in parsed_intentions
        
        if (not parse_result.get("need_invoke_actuator", True) or route == "skip_actuator") and not is_finish_intention:
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
            self.history_writer.append(interaction_ir, user_input, parse_result, slot_update_result, policy_result, act_result)
            
            save_json_atomic(self.runtime_path, interaction_ir)
            return RuntimeEvent(type="message", content=self._generate_natural_response("当前输入不进入访谈执行链。"))

        slot_update_result = self.slots_updater.update(interaction_ir, parse_result, domain_package)
        policy_result = self.policies_evaluator.evaluate(interaction_ir, parse_result, slot_update_result, domain_package)
        act_result = self.acts_planner.plan(interaction_ir, parse_result, slot_update_result, policy_result, domain_package)
        rendered_context = self.renderer.render(interaction_ir, parse_result, slot_update_result, policy_result, act_result, domain_package)
        self.history_writer.append(interaction_ir, user_input, parse_result, slot_update_result, policy_result, act_result)
        
        # Save updated state to file
        save_json_atomic(self.runtime_path, interaction_ir)
        
        # Stage 4 implementation: Check completion output
        is_completion = self._is_complete(act_result)
        
        if is_completion:
            return RuntimeEvent(
                type="complete",
                payload=self._build_result(interaction_ir, act_result, domain_package)
            )

        # Generate natural language response using internal LLM before returning to runtime
        natural_response = self._generate_natural_response(rendered_context)
        return RuntimeEvent(type="message", content=natural_response)
        
    def _generate_natural_response(self, context: str) -> str:
        messages = [
            {"role": "system", "content": "你是一个外部执行代理。严格遵守执行上下文的指示。用自然语言向用户回复。"},
            {"role": "user", "content": context}
        ]
        try:
            return self.llm_client.chat(messages)
        except Exception as e:
            return f"[内部 LLM 调用失败] {e}\n原上下文信息: {context}"

    def _is_complete(self, act_result: Dict[str, Any]) -> bool:
        # Check if the selected act type is one of the ending acts
        selected_act = act_result.get("selected_act_type")
        ending_acts = ["finish", "generate_prd", "finish_interview", "summarize_requirements"]
        return selected_act in ending_acts

    def _build_result(self, interaction_ir: Dict[str, Any], act_result: Dict[str, Any], domain_package: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "artifact_type": act_result.get("selected_act_type", "prd"),
            "artifact": "The interview is completed.",
            "structured_slots": interaction_ir.get("slots", {}),
            "checkpoint": interaction_ir.get("current_checkpoint", "completed"),
            "history_ref": "interaction_ir_history",
            "package_ref": domain_package.get("meta", {}).get("domain_id", "unknown")
        }

    def on_resume(self, payload: Dict[str, Any], runtime_context: Dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(type="message", content="Resumed")

    def on_exit(self, runtime_context: Dict[str, Any]) -> None:
        pass
