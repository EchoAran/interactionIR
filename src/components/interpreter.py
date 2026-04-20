import json
from ..models import InteractionIR, PatchProposal
from ..llm_client import LLMClient

class StateInterpreter:
    """
    状态解释器 (LLM驱动)
    职责：把最新用户输入、上一轮 act、当前状态翻译成 InteractionIR patch proposal
    """
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def interpret(self, ir: InteractionIR, external_input: str) -> PatchProposal:
        # 只提供必要的局部状态，避免超出上下文
        slot_context = {
            slot_id: {
                "status": state.status,
                "value": state.value,
                "candidates": state.candidates
            }
            for slot_id, state in ir.slot_states.items()
        }
        
        system_prompt = f"""
        你是一个专门负责解析多智能体/人机交互对话，并提出状态更新提案(Patch Proposal)的状态解释器(State Interpreter)。
        当前交互模型(InteractionIR)支持的 Slots 有:
        {json.dumps([s.model_dump() for s in ir.profile.slot_schemas], ensure_ascii=False, indent=2)}
        
        当前 Slot 的部分运行时状态:
        {json.dumps(slot_context, ensure_ascii=False, indent=2)}

        职责：
        分析用户的最新输入，判断是否提供了能够更新现有 Slot 的信息，或者提出了新的 Issue（如未解问题、分歧）。
        如果提供了确切的新值，请提出 op="update_slot_value" 补丁，并建议将对应 slot 的 op="update_slot_status" 设为 "proposed" 或 "grounded"。
        如果你觉得没有有效信息，可以返回空的 ops 列表。
        
        注意：你只是提出提案(PatchProposal)，不直接修改数据库。你的提案会被后续 Validator 拦截。
        Schema 格式:
        {{
            "ops": [
                {{"op": "update_slot_value", "target_id": "slot:target_user", "value": "内部运营人员"}},
                {{"op": "update_slot_status", "target_id": "slot:target_user", "value": "proposed"}}
            ],
            "justification": "用户明确表示目标用户是内部运营人员"
        }}
        """

        user_prompt = f"最新外部输入:\n{external_input}"
        
        proposal: PatchProposal = self.llm.generate_structured(
            system_prompt, user_prompt, PatchProposal
        )
        return proposal
