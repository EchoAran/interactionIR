from typing import Dict, Type
from handoff_runtime.agent import Agent

class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, Type[Agent]] = {}
        self._configs: Dict[str, dict] = {}

    def register(self, agent_id: str, agent_class: Type[Agent], config: dict = None):
        self._agents[agent_id] = agent_class
        if config:
            self._configs[agent_id] = config

    def get_agent_class(self, agent_id: str) -> Type[Agent]:
        if agent_id not in self._agents:
            raise ValueError(f"Agent {agent_id} not found in registry")
        return self._agents[agent_id]

    def get_config(self, agent_id: str) -> dict:
        return self._configs.get(agent_id, {})
