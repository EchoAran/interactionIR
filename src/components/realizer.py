import json
from ..models import InteractionIR, DecisionPacket, ChosenAct
from ..llm_client import LLMClient

class ResponseRealizer:
    """
    响应渲染器 (LLM驱动)
    职责：将 ChosenAct 和 DecisionPacket 翻译成面向外部 Agent 的强约束 Prompt
    """
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def realize(self, ir: InteractionIR, packet: DecisionPacket, act: ChosenAct) -> str:
        # 这里 Realizer 并不生成 JSON，而是生成一段 Prompt 文本
        # 这段文本是交给“外部 Agent”（或者你可以在本测试脚本里直接打印给人类看）
        
        system_prompt = f"""
        你是一个系统提示词生成器 (Response Realizer)。
        你需要将内部控制器的决策 (ChosenAct) 和约束 (DecisionPacket)，翻译成一段给外部访谈者 Agent 的强约束系统提示词 (Prompt)。
        
        当前内部动作决定 (ChosenAct):
        {json.dumps(act.model_dump(), ensure_ascii=False, indent=2)}
        
        当前策略约束 (DecisionPacket):
        {json.dumps(packet.model_dump(), ensure_ascii=False, indent=2)}
        
        你需要写出一段指导外部访谈者应该如何向人类发问的 Prompt 文本，不要以 JSON 返回，直接返回自然语言的 Prompt 内容。
        提示词应该包含：
        1. 角色设定
        2. 核心任务（Goal）
        3. 约束策略（如预算、不要发散等）
        """
        
        user_prompt = "请生成最终的 Prompt 给外部访谈者 Agent。"
        
        # 纯文本输出
        return self.llm.generate_text(system_prompt, user_prompt)
