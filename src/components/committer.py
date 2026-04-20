from ..models import InteractionIR, PatchProposal, SlotState, Issue
import time

class StateCommitter:
    """
    状态提交器 (Code 驱动)
    职责：将合法 Patch 和 Act 写入 InteractionIR 实例
    """
    
    def commit(self, ir: InteractionIR, patch: PatchProposal) -> InteractionIR:
        # 在真实环境，这里应该是对数据库的事务写入
        # 为了演示，我们在内存中更新传入的 IR
        
        for op in patch.ops:
            target_id = op.target_id
            
            if target_id.startswith("slot:"):
                # 初始化状态位（如果不在状态库中）
                if target_id not in ir.slot_states:
                    ir.slot_states[target_id] = SlotState(slot_id=target_id)
                
                # 应用更新
                if op.op == "update_slot_status":
                    ir.slot_states[target_id].status = op.value
                elif op.op == "update_slot_value":
                    ir.slot_states[target_id].value = op.value
                elif op.op == "add_slot":
                    # value is expected to be a dict representing slot_schema
                    # (in a real system we'd parse this strictly)
                    pass 
                    
            elif target_id.startswith("issue:"):
                if op.op == "add_issue":
                    ir.issues[target_id] = Issue(**op.value)
                elif op.op == "update_issue_status":
                    if target_id in ir.issues:
                        ir.issues[target_id].status = op.value
                        
        print(f"[Committer] 已将 {len(patch.ops)} 个变更写入 InteractionIR")
        return ir
