import os
from handoff_runtime import AgentRegistry, HandoffManager, MessageRouter, Agent, RuntimeEvent
from interaction_ir_agent import InteractionIRAgent
from llm_client import LLMClientError,build_client

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = str(BASE_DIR / ".env")

class MainAgent(Agent):
    def on_enter(self, payload: dict, ctx: dict) -> RuntimeEvent:
        return RuntimeEvent(type="message", content="MainAgent ready.")

    def on_message(self, message: str, ctx: dict) -> RuntimeEvent:
        if "需求" in message or "产品" in message:
            return RuntimeEvent(
                type="handoff",
                target_agent="requirements_interviewer",
                payload={
                    "reason": "requirements_interview",
                    "initial_user_need": message
                }
            )
        return RuntimeEvent(type="message", content=f"(Main) {message}")

    def on_resume(self, payload: dict, ctx: dict) -> RuntimeEvent:
        artifact = payload.get("artifact_type", "No artifact")
        return RuntimeEvent(
            type="message",
            content=f"主代理恢复控制权。收到访谈结果，Artifact Type: {artifact}"
        )

    def on_exit(self, ctx: dict) -> None:
        pass

def main():
    registry = AgentRegistry()
    registry.register("main_agent", MainAgent)
    
    config = {
        "domain_dir": "domain_packages",
        "package_schema_path": "packages_schema.json",
        "interactionir_schema_path": "interactionIR_schema.json",
        "dotenv_path": ".env"
    }
    registry.register("requirements_interviewer", InteractionIRAgent, config)

    manager = HandoffManager(registry)
    router = MessageRouter(manager)

    session_id = "test_session_2"
    manager.get_or_create_session(session_id, "main_agent")
    
    print("===== InteractionIR Agent Test =====")
    print("User: 你好")
    event = router.route(session_id, "你好")
    print(f"Agent: {event.content}")
    
    print("\nUser: 我想做一个产品")
    # This should trigger handoff, then on_enter of InteractionIRAgent
    # which runs the first turn and calls LLM. 
    # Since we don't have a valid .env, it might fail with LLMClientError.
    try:
        event = router.route(session_id, "我想做一个产品")
        client = build_client(DOTENV_PATH)
        messages = [
            {"role": "system", "content": "你是一个外部执行代理。严格遵守执行上下文的指示。"},
            {"role": "user", "content": event.content}
        ]
        agent_response = client.chat(messages)
        print(f"Agent: {agent_response}")
    except Exception as e:
        print(f"Expected error due to no API key: {e}")

if __name__ == "__main__":
    main()
