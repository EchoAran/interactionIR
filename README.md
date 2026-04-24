# InteractionIR

InteractionIR 是一个基于 LLM（大语言模型）和领域配置包（Domain Packages）的交互式意图解析与访谈控制系统。它通过抽象业务逻辑为领域配置包，使用户可以通过多轮对话逐步明确需求、收集信息，并在收集完成后根据预设策略执行特定动作。

## 🌟 核心特性

- **多轮访谈驱动**：根据用户的初步需求，自动选择匹配的领域配置包，并通过多轮对话逐步填充必需的信息槽位（Slots）。
- **领域配置包 (Domain Packages)**：业务逻辑高度抽象化。通过编写 JSON 格式的领域配置包，即可定义信息槽位（Slots）、意图（Intentions）、阶段（Checkpoints）、动作（Acts）和策略（Policies），无需修改核心代码。
- **智能解析与校验 (Parser & Checker)**：利用 LLM 智能解析用户的自然语言输入，识别意图并提取关键信息填充至槽位中，支持兜底提取机制。
- **动态状态机**：基于当前收集到的信息和预设条件，自动在不同的访谈阶段（Checkpoints）之间流转。
- **策略与动作生成**：根据当前阶段和槽位状态，评估并选择最合适的动作（如追问缺失信息、确认冲突信息、完成访谈等），并生成供外部代理（Agent）执行的上下文指示。

## 📂 项目结构

```text
interactionIR/
├── Creator.py               # 负责处理初始需求，选择合适的领域包，并初始化 InteractionIR 运行时状态
├── Parser_Checker.py        # 核心解析器，调用 LLM 分析用户输入，提取意图和槽位值
├── slots_Updater.py         # 槽位更新器，根据解析结果更新槽位状态，处理冲突并触发阶段流转
├── policies_Evaluator.py    # 策略评估器，评估当前状态是否满足领域包中定义的策略触发条件
├── acts_Planner.py          # 动作规划器，根据当前状态、策略和阶段，决定下一步的动作（Act）
├── Renderer.py              # 渲染器，将当前状态、策略和动作转化为给 LLM Agent 的自然语言提示词上下文
├── history_Writer.py        # 历史记录器，记录每一轮交互的详细数据
├── llm_client.py            # 封装了与 OpenAI 兼容格式 API 交互的 LLM 客户端
├── main.py                  # 项目入口文件，串联整个交互循环的控制流
├── domain_packages/         # 存放领域配置包的目录
│   └── requirements_interview.json # 示例：需求访谈领域包
├── packages_schema.json     # 领域包 JSON Schema 验证文件
├── interactionIR_schema.json# 运行时交互 IR JSON Schema 验证文件
└── .env.example             # 环境变量配置模板
```

## 🚀 快速开始

### 1. 环境准备

确保您的系统中已安装 Python 3.8+。

安装所需的依赖项（如 `requests` 等）：
```bash
pip install -r requirements.txt
```

### 2. 配置大模型 API

复制 `.env.example` 文件并重命名为 `.env`：
```bash
cp .env.example .env
```

编辑 `.env` 文件，填入您的 OpenAI 兼容 API 信息：
```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.example.com/v1
LLM_MODEL_NAME=your_model_name_here
```

### 3. 运行系统

执行主程序入口启动控制台交互：
```bash
python main.py
```

- 在第一次启动时，系统会要求您输入一个初始需求（例如："我想开发一个在线聊天室"）。
- 系统会自动匹配 `domain_packages` 下合适的领域包，并初始化 `interactionIR.runtime.json` 记录当前状态。
- 随后进入多轮交互模式。您可以在控制台输入您的回复，系统将解析您的输入，更新内部槽位，并打印出生成的代理上下文（Context），同时会调用 Agent 给您相应的回复或追问。
- 输入 `exit` 或 `quit` 即可退出系统。

## 🧩 领域包 (Domain Package) 概念

领域包是 InteractionIR 系统的灵魂，通常为一个 JSON 文件，包含以下核心模块：

- **`slot_blueprint_catalog`**: 定义了需要收集的信息槽位（如：项目目标、目标用户、成功标准等），以及它们的数据类型和初始状态。
- **`checkpoint_catalog`**: 定义了访谈的阶段（如：初始化、信息收集、确认等），以及进入该阶段的条件和在该阶段应该冻结的槽位。
- **`intention_catalog`**: 定义了用户可能的意图类型（如：回答槽位、闲聊、请求解释等）。
- **`policy_catalog`**: 定义了在特定条件满足时应触发的约束策略。
- **`act_catalog`**: 定义了系统可以执行的动作类型（如：澄清模糊信息、追问必填项、结束访谈等）。

## 📝 运行时状态 (Runtime IR)

系统在运行过程中，会在项目根目录生成 `interactionIR.runtime.json` 文件。该文件记录了当前对话的完整上下文，包括：
- 当前激活的领域包信息。
- 所有槽位的当前值、状态（unfilled, partial, filled, conflict 等）和置信度。
- 当前所处的阶段（Checkpoint）。
- 历史对话记录和每一轮的状态变更快照。

## 🛠️ 常见问题

**Q: 为什么输入内容后，没有任何槽位被提取？**
A: 请检查 LLM 的输出是否符合系统预期。`Parser_Checker.py` 会严格校验 LLM 返回的数据结构。系统已对 LLM 偶然返回 `dict` 格式的槽位做了兼容处理，并优化了 Prompt 约束。如果仍有问题，请查看控制台的 `[DEBUG]` 日志以排查 LLM 的原始输出。

**Q: 如何添加新的业务场景？**
A: 您只需在 `domain_packages` 目录下新建一个符合 `packages_schema.json` 规范的 JSON 文件，定义好您所需的 Slots、Checkpoints 和 Acts 即可。系统会在启动时自动扫描并根据用户的初始输入匹配最合适的包。

## 📄 许可证

本项目遵循相关开源协议，详情请参阅项目内相关声明。
