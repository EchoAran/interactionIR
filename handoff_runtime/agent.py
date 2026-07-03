from abc import ABC, abstractmethod
from typing import Any, Dict
from handoff_runtime.events import RuntimeEvent

class Agent(ABC):
    @abstractmethod
    def on_enter(self, payload: Dict[str, Any], runtime_context: Dict[str, Any]) -> RuntimeEvent:
        pass

    @abstractmethod
    def on_message(self, user_message: str, runtime_context: Dict[str, Any]) -> RuntimeEvent:
        pass

    @abstractmethod
    def on_resume(self, payload: Dict[str, Any], runtime_context: Dict[str, Any]) -> RuntimeEvent:
        pass

    @abstractmethod
    def on_exit(self, runtime_context: Dict[str, Any]) -> None:
        pass
