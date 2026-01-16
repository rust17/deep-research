# Deep Research Refactoring Requirements (v1.0)

## 1. Overview
Refactor the Agent workflow from a linear single-step execution to a "Batch Execute - Synthesize" pattern. This introduces a temporary buffer mechanism to improve execution efficiency and optimize context management.

## 2. Core Workflow

The system operates in a loop, with each iteration strictly following these phases:

### Phase 1: Plan & Decide
*   **Input**: User Goal, Current Plan (text), Accumulated Findings.
*   **Action**: LLM determines the current stage of the Plan and decides the next set of actions.
*   **Logic**: The LLM decides whether to gather information via Search or deepen understanding via Visit.

### Phase 2: Execute
*   **Pre-requisite**: **Clear** the `progress.md` file.
*   **Batch Operations**:
    *   **Search**: Execute web searches; append results to Progress.
    *   **Visit**: Invoke the new tool `batch_request` to visit multiple URLs concurrently; append results to Progress.
*   **Data Flow**: All raw data gathered from external tools is saved **only** to `progress.md`.

### Phase 3: Analyze & Synthesize
*   **Input**: `progress.md` (fresh raw data) + `findings.md` (historical knowledge).
*   **Action**: LLM reads the Raw Data and extracts key facts/insights.
*   **Output**: Update `findings.md` with synthesized information.

## 3. Detailed Features

### 3.1 State Manager
*   **Plan**: Remains plain text.
*   **Progress**: Defined as a **temporary buffer**. Add `clear_progress()` method.
*   **Findings**: Core knowledge base, strictly cumulative.

### 3.2 Tools
*   **`batch_request(urls: List[str])`**:
    *   New tool.
    *   Functionality: Concurrently fetch content from multiple URLs.
    *   Returns: Combined text content of all visited pages.

### 3.3 Agent Logic
*   Rewrite `run()` method to fit the `Decide -> Clear -> Execute -> Synthesize` micro-loop.
*   Enforce separation of concerns: "Acquiring Information" (Tools -> Progress) vs "Processing Information" (Progress -> Findings).
