from handoff_runtime.manager import HandoffManager
from handoff_runtime.events import RuntimeEvent

class MessageRouter:
    def __init__(self, manager: HandoffManager):
        self.manager = manager

    def route(self, session_id: str, user_message: str) -> RuntimeEvent:
        return self.manager.process_message(session_id, user_message)
