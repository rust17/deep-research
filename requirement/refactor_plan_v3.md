# 重构计划：Deep-Research 进化方案

本计划旨在将 **"Orchestrator-Driven (编排器驱动)"** 架构移植到 `deep-research` 项目中，将系统从线性执行提升为具备元认知能力的自治代理。

## 1. 核心目标
- **Orchestrator (编排器)**: 实现中央控制逻辑，支持回滚、查重和上下文压缩。
- **Structured Trace (结构化追踪)**: 全程记录 `思维 (Think) -> 动作 (Act) -> 观察 (Observe)` 的 JSON 日志。
- **Tool Registry (工具注册表)**: 解耦工具调用逻辑，实现标准化的工具执行接口。

---

## 2. 详细阶段计划

### 阶段一：基础设施增强 (Infrastructure)
1. **集成 TaskLogger**:
   - 使用已创建的 `task_logger.py`。
   - 捕获所有 LLM 输入/输出、工具参数及返回结果。
   - 目标：生成可供 `visualize-trace` (组件) 读取的兼容日志。

2. **建立 ToolRegistry**:
   - 文件：`src/deep_research/tool_manager.py`。
   - 功能：管理工具定义 (JSON Schema) 和执行映射。
   - 动作：将 `web_search` 封装为第一个标准工具。

### 阶段二：大脑重构 (Orchestrator Logic)
1. **实现 Thinking Loop (React 模式)**:
   - 重构 `agent.py`，核心逻辑转移至 `Orchestrator.run()`。
   - 提示词增强：引导 LLM 输出结构化的思考过程和工具调用。
   - 循环逻辑：`Think -> JSON Parse -> Execute Tool -> Observation -> Update Context`。

2. **自我修正机制 (Self-Correction)**:
   - **查重器**: 检测重复的搜索查询，强制 LLM 变换策略。
   - **回滚机制**: 针对格式错误或网络超时，自动触发回退 (Rollback) 并提示 LLM 修正。
   - **收敛控制**: 监控搜索增益，当信息饱和或陷入死循环时强制止损。

3. **上下文管理 (Context Management)**:
   - 实现 `ensure_context_limit()`。
   - 当 Token 接近上限时，调用 `Summarizer` 压缩历史记录，仅保留核心 Findings。

### 阶段三：交互与表现 (UI/UX)
1. **流式 CLI 增强**:
   - 在 `cli.py` 中分色显示思考过程 (Thinking) 和实际动作 (Action)。
   - 实时显示任务进度和当前搜集到的 Findings 数量。
