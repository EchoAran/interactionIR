import sys
from typing import Any, Dict
from handoff_runtime import Agent, RuntimeEvent, AgentRegistry, HandoffManager, MessageRouter

class MockInterviewAgent(Agent):
    def on_enter(self, payload: Dict[str, Any], ctx: Dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(
            type="message",
            content="我来负责需求访谈。请先描述你的产品目标。"
        )

    def on_message(self, message: str, ctx: Dict[str, Any]) -> RuntimeEvent:
        if "完成" in message:
            return RuntimeEvent(
                type="complete",
                payload={"summary": "mock interview finished"}
            )
        return RuntimeEvent(
            type="message",
            content=f"收到：{message}。请继续，或者输入'完成'结束访谈。"
        )

    def on_resume(self, payload: Dict[str, Any], ctx: Dict[str, Any]) -> RuntimeEvent:
        pass

    def on_exit(self, ctx: Dict[str, Any]) -> None:
        print("[MockInterviewAgent] Exiting...")


class MainAgent(Agent):
    def on_enter(self, payload: Dict[str, Any], ctx: Dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(type="message", content="MainAgent ready.")

    def on_message(self, message: str, ctx: Dict[str, Any]) -> RuntimeEvent:
        if "需求" in message or "产品" in message:
            return RuntimeEvent(
                type="handoff",
                target_agent="requirements_interviewer",
                payload={"reason": "requirements_interview"}
            )
        return RuntimeEvent(type="message", content=f"主代理处理：{message}")

    def on_resume(self, payload: Dict[str, Any], ctx: Dict[str, Any]) -> RuntimeEvent:
        summary = payload.get("summary", "No summary")
        return RuntimeEvent(
            type="message",
            content=f"主代理恢复控制权。收到访谈结果：{summary}"
        )

    def on_exit(self, ctx: Dict[str, Any]) -> None:
        pass


def main():
    registry = AgentRegistry()
    registry.register("main_agent", MainAgent)
    registry.register("requirements_interviewer", MockInterviewAgent)

    manager = HandoffManager(registry)
    router = MessageRouter(manager)

    session_id = "test_session_1"
    # Initialize session
    manager.get_or_create_session(session_id, "main_agent")
    
    # Initialize MainAgent explicitly by sending a dummy message or just relying on its on_message
    print("===== Handoff Runtime Test =====")
    print("User: 你好")
    event = router.route(session_id, "你好")
    print(f"Agent: {event.content}")
    
    print("\nUser: 我想做一个产品")
    event = router.route(session_id, "我想做一个产品")
    print(f"Agent: {event.content}")
    
    print("\nUser: 是一个社交产品")
    event = router.route(session_id, "是一个社交产品")
    print(f"Agent: {event.content}")
    
    print("\nUser: 完成")
    event = router.route(session_id, "完成")
    print(f"Agent: {event.content}")

if __name__ == "__main__":
    main()
