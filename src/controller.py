from .models import InteractionIR, PatchProposal, DecisionPacket, ChosenAct
from .llm_client import LLMClient
from .components.interpreter import StateInterpreter
from .components.validator import PatchValidator
from .components.evaluator import PolicyEvaluator
from .components.planner import ActPlanner
from .components.realizer import ResponseRealizer
from .components.committer import StateCommitter

class Controller:
    """
    交互控制器 (Controller)
    职责：接收外部输入，驱动内部隐式脑(InteractionIR)的状态循环，产出给外部Agent的执行提示词
    """
    
    def __init__(self, initial_ir: InteractionIR):
        self.ir = initial_ir
        
        # 初始化 LLM 客户端
        self.llm = LLMClient()
        
        # 初始化六大核心组件
        self.interpreter = StateInterpreter(self.llm)
        self.validator = PatchValidator()
        self.evaluator = PolicyEvaluator()
        self.planner = ActPlanner(self.llm)
        self.realizer = ResponseRealizer(self.llm)
        self.committer = StateCommitter()
        
    def step(self, external_input: str) -> str:
        """
        单步控制循环：Observe -> Interpret -> Validate -> Evaluate -> Plan -> Realize -> Commit
        
        :param external_input: 外部实体(Human或Agent)发来的最新消息
        :return: 渲染好的系统提示词 (Prompt)，交给外部 Agent 去执行
        """
        print(f"--- 开启控制循环 (Controller Loop) ---")
        
        # 1. 解释输入 (Interpret)
        # 将自然语言翻译为针对 InteractionIR 的补丁提案
        print("[1. Interpret] 解析外部输入中...")
        patch_proposal = self.interpreter.interpret(self.ir, external_input)
        print(f"  -> 提案包含 {len(patch_proposal.ops)} 个操作。")
        
        # 2. 校验提案 (Validate)
        # 根据状态完整性策略，过滤掉非法的操作
        print("[2. Validate] 校验提案合法性...")
        valid_patch = self.validator.validate(self.ir, patch_proposal)
        print(f"  -> 校验后剩余 {len(valid_patch.ops)} 个合法操作。")
        
        # 3. 状态提交 (Commit)
        # 提前提交合法的 Patch 到内存中的 InteractionIR (以便评估最新状态)
        print("[3. Commit] 将合法 Patch 写入内部状态库...")
        self.ir = self.committer.commit(self.ir, valid_patch)
        
        # 4. 策略评估 (Evaluate)
        # 读取更新后的 InteractionIR，根据 Policy Schema 产出面向外部的决策包
        print("[4. Evaluate] 评估策略，产出决策包...")
        decision_packet = self.evaluator.evaluate(self.ir)
        print(f"  -> 决策动作允许集合: {decision_packet.allowed_acts}")
        
        # 5. 动作规划 (Plan)
        # 在允许的动作空间内，由 LLM 挑选最高优先级的动作目标
        print("[5. Plan] 规划下一语义动作...")
        chosen_act = self.planner.plan(self.ir, decision_packet)
        print(f"  -> 决定执行动作: {chosen_act.act_type} (目标: {chosen_act.goal})")
        
        # 6. 响应渲染 (Realize)
        # 将枯燥的决策和动作结构体，翻译为外部 Agent 可以直接执行的 Prompt
        print("[6. Realize] 渲染为给外部 Agent 的 Prompt...")
        agent_prompt = self.realizer.realize(self.ir, decision_packet, chosen_act)
        
        print("--- 结束控制循环 ---\n")
        return agent_prompt
