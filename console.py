import sys
from pathlib import Path
from typing import Dict, Any

from handoff_runtime import AgentRegistry, HandoffManager, MessageRouter, Agent, RuntimeEvent
from interaction_ir_agent import InteractionIRAgent

BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = str(BASE_DIR / ".env")


class MainAgent(Agent):
    def on_enter(self, payload: Dict[str, Any], ctx: Dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(
            type="message",
            content="你好！我是主代理。输入任何与“需求”或“产品”相关的内容，我将为你切换到专门的需求访谈子代理。输入 'exit' 或 'quit' 可退出。"
        )

    def on_message(self, message: str, ctx: Dict[str, Any]) -> RuntimeEvent:
        if "需求" in message or "产品" in message:
            return RuntimeEvent(
                type="handoff",
                target_agent="requirements_interviewer",
                payload={
                    "reason": "requirements_interview",
                    "initial_user_need": message
                }
            )
        return RuntimeEvent(type="message", content=f"(主代理收到): {message}")

    def on_resume(self, payload: Dict[str, Any], ctx: Dict[str, Any]) -> RuntimeEvent:
        artifact = payload.get("artifact_type", "未知")
        return RuntimeEvent(
            type="message",
            content=f"访谈子代理已完成任务。我已重新接管会话。\n收到的结果类型: {artifact}\n你还可以继续向我发送指令。"
        )

    def on_exit(self, ctx: Dict[str, Any]) -> None:
        pass


def main() -> int:
    registry = AgentRegistry()
    registry.register("main_agent", MainAgent)
    
    config = {
        "domain_dir": "domain_packages",
        "package_schema_path": "packages_schema.json",
        "interactionir_schema_path": "interactionIR_schema.json",
        "dotenv_path": DOTENV_PATH
    }
    registry.register("requirements_interviewer", InteractionIRAgent, config)

    manager = HandoffManager(registry)
    router = MessageRouter(manager)

    session_id = "console_session_1"
    
    print("=========================================================")
    print("  InteractionIR 交互控制台 (Handoff Runtime 版) 已启动")
    print("=========================================================")
    
    # 触发并打印主代理进入消息
    session = manager.get_or_create_session(session_id, "main_agent")
    main_agent_instance = manager._get_agent_instance("main_agent")
    initial_event = main_agent_instance.on_enter({}, session.global_context)
    print(f"System> {initial_event.content}\n")

    while True:
        try:
            user_input = input("User> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            return 0

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("再见！")
            return 0

        try:
            # 路由用户消息
            event = router.route(session_id, user_input)
            
            # InteractionIRAgent 现在已经内置了 LLM 回复生成，
            # 无论是 MainAgent 还是 InteractionIRAgent，返回的 event.content 都是最终的自然语言
            if event.type == "message":
                current_agent = manager.sessions[session_id].active_agent
                print(f"Agent ({current_agent})> {event.content}\n")

            elif event.type == "complete":
                # 当子代理完成，Handoff Manager 会内部触发 on_resume 将其转换为 message 事件（在本逻辑里已处理），
                # 但以防万一直接抛出 complete 时兜底
                print(f"System> 会话已结束，产出: {event.payload}\n")
                
            elif event.type == "error":
                print(f"System Error> {event.content}\n")
                
        except Exception as exc:
            print(f"\n[运行异常] {exc}\n")

if __name__ == "__main__":
    sys.exit(main())