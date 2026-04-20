from ..models import InteractionIR, DecisionPacket

class PolicyEvaluator:
    """
    策略评估器 (Rule/Policy 驱动)
    职责：结合 Profile 的 Policy Schema，计算出面向外部 Agent 的动态约束 (DecisionPacket)
    """
    
    def evaluate(self, ir: InteractionIR) -> DecisionPacket:
        # 这里用 Python 逻辑模拟 Rego/OPA 引擎
        # 实际情况应该解析 ir.profile.policies 中的规则表达式
        
        allowed_acts = ir.profile.allowed_act_types.copy()
        blocked_acts = []
        focus_slots = []
        notes = []
        decision = "require_input"
        
        # 简单逻辑：如果必填项（核心事实槽）还没收集全，只允许澄清和问事实
        missing_core_slots = []
        for schema in ir.profile.slot_schemas:
            if schema.kind == "fact_slot":
                state = ir.slot_states.get(schema.slot_id)
                if not state or state.status in ["empty", "proposed"]:
                    missing_core_slots.append(schema.slot_id)
                    
        if missing_core_slots:
            focus_slots.extend(missing_core_slots)
            allowed_acts = [act for act in allowed_acts if act in ["ask_fact", "clarify_term"]]
            blocked_acts = ["summarize_understanding", "freeze_slot"]
            notes.append("核心信息不足，优先追问缺失的事实槽位。")
        else:
            # 如果都收齐了，可以提议总结或冻结
            allowed_acts = [act for act in allowed_acts if act in ["summarize_understanding", "freeze_slot", "surface_conflict"]]
            notes.append("核心信息已就绪，可进行总结或解决潜在冲突。")
            
        # 如果当前有未解决的 Issue（如冲突、疑问）
        open_issues = [issue_id for issue_id, issue in ir.issues.items() if issue.status == "open"]
        if open_issues:
            if "surface_conflict" in ir.profile.allowed_act_types:
                allowed_acts.append("surface_conflict")
            notes.append("当前存在未解决的 Issue，请优先消解分歧。")
            
        return DecisionPacket(
            decision=decision,
            allowed_acts=list(set(allowed_acts)),
            blocked_acts=blocked_acts,
            focus_slots=list(set(focus_slots)),
            question_budget=2,
            notes_for_agent=notes
        )
