from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

class RuntimeEvent(BaseModel):
    type: Literal["message", "handoff", "complete", "error"]
    content: Optional[str] = None
    target_agent: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
