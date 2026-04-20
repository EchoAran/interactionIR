import json
from ..models import InteractionIR, DecisionPacket, ChosenAct
from ..llm_client import LLMClient

class ActPlanner:
    """
    动作规划器 (LLM驱动)
    职责：在 allowed_acts 空间内，挑选当前优先级最高的动作生成 Chosen Act
    """
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def plan(self, ir: InteractionIR, packet: DecisionPacket) -> ChosenAct:
        system_prompt = f"""
        你是一个专门负责根据约束决定交互策略的动作规划器(Act Planner)。
        你必须在 Evaluator 给定的 `allowed_acts` 空间内，挑选出当前优先级最高的一项动作，生成 ChosenAct。
        
        当前 Controller 产出的约束包(DecisionPacket):
        {json.dumps(packet.model_dump(), ensure_ascii=False, indent=2)}
        
        你要解决的 Focus Slots: {packet.focus_slots}
        允许你选择的 Act: {packet.allowed_acts}
        
        Schema 格式:
        {{
            "act_type": "ask_fact",
            "about_slots": ["slot:target_user"],
            "goal": "向受访者询问系统的目标用户是谁"
        }}
        """

        user_prompt = "请根据当前的约束和需要聚焦的槽位，规划下一步的动作 (ChosenAct)。"
        
        chosen_act: ChosenAct = self.llm.generate_structured(
            system_prompt, user_prompt, ChosenAct
        )
        
        # 做一个简单的容错校验，如果 LLM 选了不允许的，降级为一个安全默认值
        if chosen_act.act_type not in packet.allowed_acts:
            chosen_act.act_type = packet.allowed_acts[0] if packet.allowed_acts else "ask_fact"
            
        return chosen_act
