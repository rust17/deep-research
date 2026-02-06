import json
from datetime import datetime
from typing import Any

from .llm_client import LLMClient
from .stream_handler import EventType, StreamHandler
from .task_logger import TaskLogger
from .tool_manager import ToolRegistry
from .tools.search import web_search

# 定义 Orchestrator 专用的 Prompt
ORCHESTRATOR_SYSTEM_PROMPT = """You are a deep research assistant powered by a "Think-Act-Observe" loop.
Your goal is to answer the user's request comprehensively by gathering information and verifying facts.

### Core Instructions
1. **Think**: Before taking any action, analyze the current state. What do you know? What is missing? What is the best next step?
2. **Act**: Use available tools to gather information. Prefer specific queries over broad ones.
3. **Observe**: Analyze the tool output. Does it answer the question? Do you need to pivot?

### Constraints
- **Anti-Hallucination**: Do not make up facts. If you don't know, search.
- **No Duplication**: Check your history. Do not repeat the same search query.
- **Efficiency**: If you have enough information, stop and provide the final answer.

### Output Format
You MUST strictly output a JSON object in the following format:
{
    "thought": "Your reasoning process. Be specific about what you are looking for and why.",
    "action": "Name of the tool to use. Use 'finish' when you have the final answer.",
    "parameters": {
        // Parameters for the tool.
        // If action is 'finish', use: {"answer": "Your final comprehensive report..."}
    }
}
"""


class Orchestrator:
    def __init__(self, user_goal: str, max_loops: int = 15, stream_handler: StreamHandler = None):
        self.user_goal = user_goal
        self.max_loops = max_loops
        self.stream_handler = stream_handler

        self.llm = LLMClient()
        self.logger = TaskLogger(goal=user_goal)
        self.tool_registry = ToolRegistry()

        # Register Tools
        self._register_tools()

        # Context Management
        self.history: list[dict[str, Any]] = []
        self.long_term_memory: str = ""  # Summary of past events

    def _emit(self, event_type: EventType, data: dict[str, Any] = None):
        if self.stream_handler:
            self.stream_handler.emit(event_type, data)

    def _register_tools(self):
        # Register web_search
        # 注意：这里我们重新封装 web_search 以符合 Tool 接口，或者直接使用
        # 考虑到 web_search 目前返回的是字符串摘要，这符合我们的需求
        self.tool_registry.register_function(
            name="web_search",
            description="Search the internet for information. Returns a summary of findings.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query."}},
                "required": ["query"],
            },
        )(web_search)

    def run(self) -> str:
        """Main execution loop."""
        self._emit(EventType.WORKFLOW_START, {"goal": self.user_goal})

        loop_count = 0
        final_answer = ""

        while loop_count < self.max_loops:
            loop_count += 1

            # 1. Build Context & Prompt
            prompt = self._build_prompt()

            # 2. LLM Call (Think)
            try:
                response = self._get_llm_response(prompt)
            except Exception as e:
                self._emit(EventType.ERROR, {"message": f"LLM Error: {e}"})
                self.logger.log_step("error", "LLM Failure", str(e))
                continue

            # 3. Parse Response
            thought = response.get("thought", "")
            action = response.get("action", "")
            params = response.get("parameters", {})

            # Log Thought
            self._emit(EventType.AGENT_THINK, {"thought": thought, "step": loop_count})
            self.logger.log_step("thought", "Reasoning", thought)

            # Check for Finish
            if action == "finish":
                final_answer = params.get("answer", "No answer provided.")
                self._emit(EventType.WORKFLOW_END, {"result": final_answer})
                self.logger.log_step("finish", "Completion", final_answer)
                self.logger.finish(result=final_answer)
                return final_answer

            # 4. Execute Tool (Act)
            result = self._execute_tool(action, params)

            # 5. Observe & Update History
            observation_entry = {
                "step": loop_count,
                "thought": thought,
                "action": action,
                "parameters": params,
                "observation": result,
            }
            self.history.append(observation_entry)
            self._emit(EventType.STEP_COMPLETE, {"step": loop_count, "observation": result})

            # Context Compression (Simple implementation)
            self._manage_context()

        # Fallback if loop limit reached
        fallback_msg = "Reached maximum steps without a final answer."
        self._emit(EventType.WARNING, {"message": fallback_msg})
        final_report = self._synthesize_final_report()
        self._emit(EventType.WORKFLOW_END, {"result": final_report})
        return final_report

    def _build_prompt(self) -> str:
        """Constructs the prompt with history."""
        # Get Tool Definitions
        tools_schema = json.dumps(self.tool_registry.get_tools_schema(), indent=2)

        # Format History
        history_str = ""
        for item in self.history:
            history_str += f"\nStep {item['step']}:\n"
            history_str += f"Thought: {item['thought']}\n"
            history_str += f"Action: {item['action']}({json.dumps(item['parameters'])})\n"
            # Truncate observation
            obs_preview = str(item["observation"])[:500]
            history_str += f"Observation: {obs_preview}...\n"

        # Memory Section
        memory_section = ""
        if self.long_term_memory:
            memory_section = f"\n### Long-term Memory (Summarized Past)\n{self.long_term_memory}\n"

        prompt = f"""
{ORCHESTRATOR_SYSTEM_PROMPT}

Current Date: {datetime.now().strftime("%Y-%m-%d")}
User Goal: {self.user_goal}

### Available Tools
{tools_schema}
{memory_section}
### Execution History
{history_str}

Please provide your next step in JSON format.
"""
        return prompt

    def _get_llm_response(self, prompt: str) -> dict[str, Any]:
        """Wrapper to handle JSON parsing and retries."""
        attempts = 0
        max_attempts = 3

        while attempts < max_attempts:
            try:
                # Assuming llm.query_json handles basic JSON cleaning
                return self.llm.query_json(prompt)
            except Exception as e:
                attempts += 1
                self._emit(
                    EventType.WARNING,
                    {"message": f"JSON parsing failed ({attempts}/{max_attempts}). Retrying..."},
                )
                if attempts == max_attempts:
                    raise e
        return {}

    def _execute_tool(self, action: str, params: dict[str, Any]) -> str:
        """Executes the tool and logs the result."""
        # Self-Correction: Check for duplicates
        if self._is_duplicate_action(action, params):
            return (
                "Error: You have already executed this exact action with these parameters. "
                "Please try a different query or strategy."
            )

        try:
            self._emit(EventType.TOOL_START, {"tool": action, "parameters": params})
            self.logger.log_step("tool_call", action, params)

            start_time = datetime.now()
            result = self.tool_registry.execute(action, params)
            duration = (datetime.now() - start_time).total_seconds()

            self._emit(
                EventType.TOOL_END,
                {"tool": action, "result": result, "duration": duration, "status": "success"},
            )
            self.logger.log_step("tool_result", action, result)

            return result
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            self._emit(
                EventType.TOOL_END,
                {"tool": action, "error": error_msg, "status": "error"},
            )
            self.logger.log_step("error", action, error_msg)
            return error_msg

    def _is_duplicate_action(self, action: str, params: dict[str, Any]) -> bool:
        """Check if this action has been performed recently."""
        for item in self.history:
            if item["action"] == action and item["parameters"] == params:
                self._emit(
                    EventType.WARNING, {"message": f"Detected duplicate action: {action} {params}"}
                )
                return True
        return False

    def _manage_context(self):
        """
        Context Management:
        If history is too long, summarize the oldest steps and append to long_term_memory.
        """
        MAX_HISTORY = 5

        if len(self.history) > MAX_HISTORY:
            # Pop the oldest items to summarize
            steps_to_summarize = self.history[:-MAX_HISTORY]
            self.history = self.history[-MAX_HISTORY:]

            summary_prompt = f"""
            Please summarize the following research steps into a concise paragraph.
            Focus on the key findings and actions taken.

            Current Long-term Memory:
            {self.long_term_memory}

            New Steps to Summarize:
            {json.dumps(steps_to_summarize, indent=2)}
            """

            try:
                self._emit(
                    EventType.INFO,
                    {"message": "Compressing context and updating long-term memory..."},
                )
                new_summary = self.llm.query(summary_prompt, model_type="small")
                self.long_term_memory = new_summary
                self._emit(EventType.INFO, {"message": "Context compressed successfully."})
            except Exception as e:
                self._emit(EventType.ERROR, {"message": f"Context compression failed: {e}"})

    def _synthesize_final_report(self) -> str:
        """Force a final synthesis if loop ends."""
        # Similar to the original agent's report generation
        prompt = f"""
        User Goal: {self.user_goal}
        History: {json.dumps(self.history, indent=2, ensure_ascii=False)}

        Please generate a comprehensive report based on the history above.
        """
        return self.llm.query(prompt)
