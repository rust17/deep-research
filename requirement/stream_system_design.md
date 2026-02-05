# 事件驱动架构优化设计方案 (Stream System)

**目标**：将 `deep-research` 从简单的文本流重定向输出升级为结构化事件驱动架构。
**收益**：使前端 (Streamlit) 能够区分并结构化展示“思考过程”、“工具执行”、“系统通知”，实现更高级的 UI 交互（如折叠日志、状态 Spinner 等）。

---

## 1. 核心概念：事件总线 (Event Bus)

不再直接打印到 `console`，而是通过 `StreamHandler` 发射事件。

### 定义事件类型 (Event Types)
- `WORKFLOW_START`: 调研任务启动。
- `AGENT_THINK`: 代理思考过程 (支持流式内容更新)。
- `TOOL_START`: 工具开始调用 (包含工具名和参数)。
- `TOOL_END`: 工具调用结束 (包含返回结果、耗时、状态)。
- `STEP_COMPLETE`: 完成一个完整的 Think-Act 循环。
- `ERROR`: 发生异常或 LLM 解析错误。
- `WORKFLOW_END`: 生成最终报告并结束任务。

---

## 2. 架构组件

### 2.1 StreamHandler (`stream_handler.py`)
- **职责**: 作为 Orchestrator 和 UI 之间的中介。
- **机制**:
  - `emit(event_type, data)`: 后端触发事件。
  - `subscribe(callback)`: 前端注册监听器处理事件。

### 2.2 Orchestrator 集成
- 移除 `orchestrator.py` 中耦合的 `console.print` 逻辑。
- 在循环的关键节点（获取 LLM 响应后、执行工具前后、压缩上下文后）注入事件发送点。

### 2.3 GUI 适配 (`gui.py`)
- 不再使用 `sys.stdout` 重定向黑盒。
- 根据事件类型渲染不同的 UI 组件：
  - **Thought**: 使用 `st.chat_message("assistant")` 或 `st.expander` 展示。
  - **Action**: 使用 `st.status()` 动态显示正在进行的工具调用。
  - **Result**: 在状态组件完成后展示预览。
