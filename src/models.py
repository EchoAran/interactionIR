from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, Field

# ==========================================
# 第一层：InteractionIR 静态定义 (Schema / Base)
# ==========================================

class SlotSchema(BaseModel):
    slot_id: str
    kind: Literal["fact_slot", "commitment_slot", "decision_slot", "assumption_slot"]
    semantic_type: str = "text"
    extension_policy: Literal["fixed", "extensible", "controller_proposed"] = "fixed"
    description: Optional[str] = None

class PolicySchema(BaseModel):
    policy_id: str
    type: Literal["state_integrity", "interaction_progress", "evidence_required", "schema_evolution"]
    severity: Literal["hard_block", "soft_warn"]
    description: str

class DomainProfile(BaseModel):
    profile_id: str
    slot_schemas: List[SlotSchema]
    allowed_act_types: List[str]
    policies: List[PolicySchema]
    checkpoints: List[str]

# ==========================================
# 第二层：InteractionIR 运行时状态 (Runtime State)
# ==========================================

class Party(BaseModel):
    party_id: str
    party_type: Literal["human", "agent", "tool_proxy"]
    role: str
    authority_scope: List[str] = Field(default_factory=list)

class Provenance(BaseModel):
    source_kind: Literal["user_input", "act", "external_tool", "inference"]
    source_id: Optional[str] = None

class SlotState(BaseModel):
    slot_id: str
    status: Literal["empty", "proposed", "grounded", "contested", "frozen", "waived"] = "empty"
    value: Optional[Any] = None
    candidates: List[Any] = Field(default_factory=list)
    provenance: Optional[Provenance] = None

class Issue(BaseModel):
    issue_id: str
    kind: Literal["open_question", "conflict", "assumption", "risk"]
    status: Literal["open", "mitigated", "resolved", "waived"] = "open"
    title: str
    related_slots: List[str] = Field(default_factory=list)

class ActLog(BaseModel):
    act_id: str
    act_type: str
    sender_party_id: str
    about_slots: List[str] = Field(default_factory=list)
    payload: Dict[str, Any]

class CheckpointState(BaseModel):
    checkpoint_id: str
    status: Literal["pending", "reached"] = "pending"

class InteractionIR(BaseModel):
    """
    完整的 InteractionIR 状态模型，Controller 独占的内部状态机
    """
    interaction_id: str
    profile: DomainProfile
    parties: List[Party] = Field(default_factory=list)
    slot_states: Dict[str, SlotState] = Field(default_factory=dict)
    issues: Dict[str, Issue] = Field(default_factory=dict)
    acts: List[ActLog] = Field(default_factory=list)
    checkpoints: Dict[str, CheckpointState] = Field(default_factory=dict)


# ==========================================
# 第三层：Controller 内部通信对象 (Patch, Packet)
# ==========================================

class PatchOp(BaseModel):
    op: Literal["add_slot", "update_slot_status", "update_slot_value", "add_issue", "update_issue_status", "mark_checkpoint"]
    target_id: str  # slot_id, issue_id or checkpoint_id
    value: Any

class PatchProposal(BaseModel):
    """State Interpreter 的输出，用于申请状态更新"""
    ops: List[PatchOp] = Field(default_factory=list)
    justification: str

class DecisionPacket(BaseModel):
    """Policy Evaluator 的输出，面向外部的动态策略"""
    decision: Literal["require_input", "allow", "require_tool_query", "require_review", "block"]
    allowed_acts: List[str]
    blocked_acts: List[str] = Field(default_factory=list)
    focus_slots: List[str] = Field(default_factory=list)
    question_budget: int = 1
    notes_for_agent: List[str] = Field(default_factory=list)

class ChosenAct(BaseModel):
    """Act Planner 的输出，面向外部的具体动作指令"""
    act_type: str
    about_slots: List[str]
    goal: str
