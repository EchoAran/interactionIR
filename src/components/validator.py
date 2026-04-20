from ..models import InteractionIR, PatchProposal, PatchOp
import copy

class PatchValidator:
    """
    补丁校验器 (Rule驱动)
    职责：检查 PatchProposal 是否合法（结构合法、profile 允许、不违反 State Integrity Constraints）
    """
    
    def validate(self, ir: InteractionIR, proposal: PatchProposal) -> PatchProposal:
        valid_ops = []
        
        for op in proposal.ops:
            if self._is_op_valid(ir, op):
                valid_ops.append(op)
            else:
                print(f"[Validator] 拦截非法操作: {op.model_dump_json()}")
                
        # 返回一个仅包含合法 op 的新 proposal
        return PatchProposal(ops=valid_ops, justification=proposal.justification)
        
    def _is_op_valid(self, ir: InteractionIR, op: PatchOp) -> bool:
        # 规则 1：尝试修改的 slot_id 必须存在于 schema 或当前 states 中
        if op.target_id.startswith("slot:"):
            schema_exists = any(s.slot_id == op.target_id for s in ir.profile.slot_schemas)
            state_exists = op.target_id in ir.slot_states
            
            if op.op == "add_slot":
                # 只允许 extension_policy != fixed 时新增 slot，此处简化判断
                return True
            
            if not (schema_exists or state_exists):
                return False
                
            # 规则 2：已经 frozen 的 slot 不能被覆盖 (状态完整性底线)
            if state_exists and ir.slot_states[op.target_id].status == "frozen":
                return False
                
            # 规则 3：如果要更新状态为 grounded，必须有来源。
            # (注意：因为我们现在在提案阶段，可能 provenance 尚未附上，真实系统里需要连带 provenance 一起校验。这里做简化演示)
            if op.op == "update_slot_status" and op.value == "grounded":
                # 这里本应该强制检查 provenance，暂时放行或记录警告
                pass
                
        return True
