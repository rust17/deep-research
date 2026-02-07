# Deep Research 系统架构

## 核心状态与工具
- **Findings**: 存储研究发现的知识点（追加模式）。
- **Plan**: 当前待执行的任务列表和优先级。
- **Progress**: 历史操作记录，用于防止陷入死循环。
- **Tools**: `web_search` (搜索引擎), `visit_page` (抓取网页内容), `read_file`, `write_file`.

## 流程逻辑

### 1. 初始化 (Initialize)
- 输入：用户研究目标 (User Goal)
- 生成初始计划：`LLM -> init_plan(User Goal)` -> 保存至 `tasks/plan.md`
- 初始化空文件：`tasks/findings.md`, `tasks/progress.md`

### 2. 研究循环 (Main Loop)
`while loop_count < max_loops:`

  #### A. 读取上下文 (Read Context)
  - 加载 `User Goal`, `tasks/plan.md`, `tasks/progress.md` 以及最近的 `tasks/findings.md`。

  #### B. 决策与行动 (Action Selection)
  - `LLM -> decide_next_step(Context)`
  - 决策结果可能是：
    1. **Tool Call**: 调用 `web_search` 或 `visit_page`。
    2. **Synthesize**: 处理搜集到的原始数据，提取关键点并追加到 `tasks/findings.md`。
    3. **Refine Plan**: 发现新线索后，修改 `tasks/plan.md`。

  #### C. 执行与更新 (Execute & Update)
  - 执行上述决策并捕获结果（Observation）。
  - 更新 `tasks/progress.md` 记录本次操作及结果状态。
  - 异常处理：若工具调用失败，记录错误并标记在下一次循环中重试或调整方案。

  #### D. 终止检查 (Termination Check)
  - `LLM -> check_goal_met(User Goal, Findings)`
  - 如果目标达成或达到最大循环次数，跳出循环。

### 3. 生成报告 (Final Report)
- `LLM -> generate_report(User Goal, Findings)`
- 输出一份结构完整的 Markdown 研究报告。
