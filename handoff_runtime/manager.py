from typing import Any, Dict
from handoff_runtime.session import HandoffSession, HandoffStackItem
from handoff_runtime.events import RuntimeEvent
from handoff_runtime.registry import AgentRegistry
from handoff_runtime.agent import Agent

class HandoffManager:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.sessions: Dict[str, HandoffSession] = {}
        self.agent_instances: Dict[str, Agent] = {}

    def get_or_create_session(self, session_id: str, initial_agent: str) -> HandoffSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = HandoffSession(
                session_id=session_id,
                active_agent=initial_agent
            )
        return self.sessions[session_id]

    def _get_agent_instance(self, agent_id: str) -> Agent:
        if agent_id not in self.agent_instances:
            agent_class = self.registry.get_agent_class(agent_id)
            config = self.registry.get_config(agent_id)
            # Support both constructors with and without config
            try:
                self.agent_instances[agent_id] = agent_class(config)
            except TypeError:
                self.agent_instances[agent_id] = agent_class()
        return self.agent_instances[agent_id]

    def process_message(self, session_id: str, user_message: str) -> RuntimeEvent:
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.sessions[session_id]
        active_agent_id = session.active_agent
        agent = self._get_agent_instance(active_agent_id)
        
        event = agent.on_message(user_message, session.global_context)
        return self._handle_event(session, event)

    def _handle_event(self, session: HandoffSession, event: RuntimeEvent) -> RuntimeEvent:
        if event.type == "handoff":
            return self._execute_handoff(session, event)
        elif event.type == "complete":
            return self._execute_complete(session, event)
        else:
            return event

    def _execute_handoff(self, session: HandoffSession, event: RuntimeEvent) -> RuntimeEvent:
        if not event.target_agent:
            return RuntimeEvent(type="error", content="Handoff target_agent not specified")
        
        current_agent_id = session.active_agent
        target_agent_id = event.target_agent
        
        # Push current to stack
        session.handoff_stack.append(HandoffStackItem(
            agent_id=current_agent_id,
            reason=event.payload.get("reason", "")
        ))
        
        # Update active agent
        session.active_agent = target_agent_id
        
        # Trigger on_enter
        target_agent = self._get_agent_instance(target_agent_id)
        new_event = target_agent.on_enter(event.payload, session.global_context)
        
        # Handle the event returned by on_enter (could be message, handoff, complete)
        return self._handle_event(session, new_event)

    def _execute_complete(self, session: HandoffSession, event: RuntimeEvent) -> RuntimeEvent:
        current_agent_id = session.active_agent
        current_agent = self._get_agent_instance(current_agent_id)
        current_agent.on_exit(session.global_context)
        
        if not session.handoff_stack:
            # Reached root, session complete
            return event
        
        # Pop from stack
        previous_item = session.handoff_stack.pop()
        previous_agent_id = previous_item.agent_id
        session.active_agent = previous_agent_id
        
        # Trigger on_resume
        previous_agent = self._get_agent_instance(previous_agent_id)
        new_event = previous_agent.on_resume(event.payload, session.global_context)
        
        return self._handle_event(session, new_event)
