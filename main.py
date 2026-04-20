import json
from src.models import (
    InteractionIR, DomainProfile, SlotSchema, PolicySchema, Party
)
from src.controller import Controller

def create_initial_ir() -> InteractionIR:
    """创建初始的 InteractionIR 状态模型"""
    
    # 1. 静态定义: Profile (Schema/Base)
    profile = DomainProfile(
        profile_id="requirements_interview/v1",
        slot_schemas=[
            SlotSchema(slot_id="slot:problem_statement", kind="fact_slot", description="核心问题陈述"),
            SlotSchema(slot_id="slot:target_user", kind="fact_slot", description="系统的目标用户是谁"),
            SlotSchema(slot_id="slot:budget", kind="fact_slot", description="项目的可用预算"),
        ],
        allowed_act_types=["ask_fact", "clarify_term", "summarize_understanding", "surface_conflict"],
        policies=[
            PolicySchema(
                policy_id="policy:missing_core_slots_priority",
                type="interaction_progress",
                severity="soft_warn",
                description="缺失核心事实信息时，优先执行问询或澄清动作。"
            )
        ],
        checkpoints=["context_seeded", "core_problem_aligned"]
    )
    
    # 2. 运行时状态: Parties & Slots
    parties = [
        Party(party_id="party:human_pm", party_type="human", role="requester"),
        Party(party_id="party:interviewer_agent", party_type="agent", role="interviewer")
    ]
    
    # 初始化 InteractionIR
    ir = InteractionIR(
        interaction_id="int:req_interview:001",
        profile=profile,
        parties=parties
    )
    
    return ir


if __name__ == "__main__":
    print("=== 初始化 InteractionIR 控制器 ===")
    ir = create_initial_ir()
    controller = Controller(initial_ir=ir)
    
    # 模拟第一次人类输入
    human_input_1 = "我们要开发一个系统，主要给内部运营同事用，希望界面简单点，少点人工干预。"
    
    print(f"\n[外部输入 1] Human: {human_input_1}\n")
    agent_prompt_1 = controller.step(human_input_1)
    
    print("\n===========================================")
    print(">> Controller 产出给 External Agent 的最终 Prompt:")
    print("===========================================")
    print(agent_prompt_1)
    print("===========================================\n")
    
    # 查看内部隐式状态的变化
    print(">> Controller 内部 InteractionIR 当前的 Slot 状态:")
    print(json.dumps(
        {k: v.model_dump() for k, v in controller.ir.slot_states.items()}, 
        ensure_ascii=False, indent=2
    ))
