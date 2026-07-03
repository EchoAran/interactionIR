from typing import Any, Dict, List
from pydantic import BaseModel, Field

class HandoffStackItem(BaseModel):
    agent_id: str
    reason: str = ""

class HandoffSession(BaseModel):
    session_id: str
    active_agent: str
    handoff_stack: List[HandoffStackItem] = Field(default_factory=list)
    agent_states: Dict[str, Any] = Field(default_factory=dict)
    global_context: Dict[str, Any] = Field(default_factory=dict)
