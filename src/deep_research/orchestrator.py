import json
import time
from datetime import datetime
from typing import Any

from .llm_client import LLMClient
from .prompt import REPORT_SUMMARIZE_PROMPT
from .stream_handler import Event, Pulse, StreamHandler
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

    def _emit(
        self, event: Event, content: Any = None, name: str = "", metadata: dict = None
    ) -> Pulse:
        """创建脉冲并发送，隐藏 Pulse 构建细节。"""
        pulse = Pulse(
            type=event,
            content=content,
            name=name,
            metadata=metadata or {},
        )
        if self.stream_handler:
            self.stream_handler.emit(pulse)
        return pulse

    def _register_tools(self):
        # Register web_search
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
        self._emit(Event.INIT, {"goal": self.user_goal})

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
                msg = f"LLM Error: {e}"
                self._emit(Event.ERROR, msg)
                self.logger.step(Event.ERROR, "LLM Failure", msg)
                continue

            # 3. Parse Response
            thought = response.get("thought", "")
            action = response.get("action", "")
            params = response.get("parameters", {})

            # Log Thought
            self._emit(Event.THOUGHT, thought, metadata={"step": loop_count})
            self.logger.step(Event.THOUGHT, "Reasoning", thought)

            # Check for Finish
            if action == "finish":
                final_answer_hint = params.get("answer", "")
                self._emit(Event.INFO, "Agent decided to finish. Synthesizing final report...")
                final_report = self._generate_final_report(final_answer_hint)
                self._emit(Event.FINISH, final_report)
                self.logger.step(Event.FINISH, "Completion", final_report)
                self.logger.finish(result=final_report)
                return final_report

            # 4. Execute Tool (Act)
            result = self._execute_tool(action, params)

            # 5. Observe & Update History
            pulse = self._emit(
                Event.STEP,
                content={
                    "thought": thought,
                    "action": action,
                    "parameters": params,
                    "observation": result,
                },
                name=f"Step {loop_count}",
                metadata={"step": loop_count},
            )
            self.history.append(pulse.to_dict())

            self._manage_context()

        # Fallback if loop limit reached
        fallback_msg = "Reached maximum steps without a final answer."
        self._emit(Event.WARN, fallback_msg)
        final_report = self._generate_final_report()
        self._emit(Event.FINISH, final_report)
        return final_report

    def _build_prompt(self) -> str:
        """Constructs the prompt with history."""
        # Get Tool Definitions
        tools_schema = json.dumps(self.tool_registry.get_tools_schema(), indent=2)

        # Format History
        history_str = ""
        for entry in self.history:
            item = entry["content"]
            step_num = entry["metadata"].get("step", "?")
            history_str += f"\nStep {step_num}:\n"
            history_str += f"Thought: {item['thought']}\n"
            history_str += f"Action: {item['action']}({json.dumps(item['parameters'])})\n"
            # Truncate observation
            obs_preview = str(item["observation"])
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
                    Event.WARN,
                    f"JSON parsing failed ({attempts}/{max_attempts}). Retrying...",
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
            self._emit(Event.ACTION, params, name=action)
            self.logger.step(Event.ACTION, action, params)

            start_time = datetime.now()
            result = self.tool_registry.execute(action, params)
            duration = (datetime.now() - start_time).total_seconds()

            self._emit(Event.OBSERVATION, result, name=action, metadata={"duration": duration})
            self.logger.step(Event.OBSERVATION, action, result)

            return result
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            self._emit(Event.ERROR, error_msg, name=action)
            self.logger.step(Event.ERROR, action, error_msg)
            return error_msg

    def _is_duplicate_action(self, action: str, params: dict[str, Any]) -> bool:
        """Check if this action has been performed recently."""
        for entry in self.history:
            item = entry["content"]
            if item["action"] == action and item["parameters"] == params:
                self._emit(Event.WARN, f"Detected duplicate action: {action} {params}")
                return True
        return False

    def _manage_context(self):
        """
        Context Management:
        If the current context (prompt) size approaches the model's limit,
        summarize the oldest steps and update long_term_memory.
        """
        current_prompt = self._build_prompt()
        token_count = self.llm.count_tokens(current_prompt)
        limit = self.llm.get_context_limit()
        threshold = int(limit * 0.8)

        if token_count > threshold:
            self._emit(
                Event.INFO,
                f"Context size ({token_count} tokens) exceeds threshold ({threshold}). Compressing...",
            )

            # Keep the most recent 2 steps, summarize the rest
            steps_to_summarize = self.history[:-2]
            self.history = self.history[-2:]

            summary_prompt = f"""
            Please summarize the following research steps into a concise paragraph.
            Focus on the key findings and actions taken.

            Current Long-term Memory:
            {self.long_term_memory}

            New Steps to Summarize:
            {json.dumps(steps_to_summarize, indent=2)}
            """

            try:
                self._emit(Event.INFO, "Compressing context and updating long-term memory...")
                new_summary = self.llm.query(summary_prompt)
                self.long_term_memory = new_summary
                self._emit(Event.INFO, "Context compressed successfully.")
            except Exception as e:
                self._emit(Event.ERROR, f"Context compression failed: {e}")

    def _generate_final_report(self, final_answer_hint: str = "") -> str:
        """Force a final synthesis if loop ends or agent finishes."""
        # Format History for synthesis
        history_str = ""
        for entry in self.history:
            item = entry["content"]
            step_num = entry["metadata"].get("step", "?")
            history_str += f"\nStep {step_num}:\n"
            history_str += f"Thought: {item['thought']}\n"
            history_str += f"Action: {item['action']}({json.dumps(item['parameters'])})\n"
            # Include more of the observation for the final report
            obs_preview = str(item["observation"])
            history_str += f"Observation: {obs_preview}\n"

        if final_answer_hint:
            history_str += f"\nAgent's preliminary conclusion: {final_answer_hint}\n"

        # Memory Section
        memory_section = ""
        if self.long_term_memory:
            memory_section = f"\n### Long-term Memory (Summarized Past)\n{self.long_term_memory}\n"

        prompt = f"""
### Execution History
{history_str}
{memory_section}

{REPORT_SUMMARIZE_PROMPT.format(user_goal=self.user_goal)}
"""
        return self.llm.query(prompt)
