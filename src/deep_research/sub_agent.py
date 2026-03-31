import json
import threading
from datetime import datetime
from typing import Any

from .llm_client import LLMClient
from .log import log
from .prompt import SUB_AGENT_SUMMARIZE_PROMPT, SUB_AGENT_SYSTEM_PROMPT
from .stream_handler import Event, Pulse, StreamHandler
from .tool_manager import ToolRegistry


class SubAgent:
    def __init__(
        self,
        sub_task: str,
        max_loops: int = 10,
        stream_handler: StreamHandler = None,
        stop_event: threading.Event = None,
    ):
        self.sub_task = sub_task
        self.max_loops = max_loops
        self.stream_handler = stream_handler
        self.stop_event = stop_event

        self.llm = LLMClient()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_search_and_visit()

        # Context Management
        self.message_history: list[dict[str, str]] = []
        self._init_history()

    def _init_history(self):
        """Initialize message history with system prompt and sub-task."""
        system_content = SUB_AGENT_SYSTEM_PROMPT.format(
            tools_schema=json.dumps(self.tool_registry.get_tools_schema(), ensure_ascii=False)
        )

        self.message_history.append({"role": "system", "content": system_content})

        user_init_msg = f"Current Date: {datetime.now().strftime('%Y-%m-%d')}\nYour assigned sub-task is:\n{self.sub_task}\nPlease begin your investigation."
        self.message_history.append({"role": "user", "content": user_init_msg})

    def _emit(
        self, event: Event, content: Any = None, name: str = "", metadata: dict = None
    ) -> Pulse | None:
        if not self.stream_handler:
            return None

        pulse = Pulse(
            type=event,
            content=content,
            name=f"[SubAgent] {name}",
            metadata=metadata or {},
        )
        self.stream_handler.emit(pulse)
        return pulse

    def run(self) -> str:
        """Main execution loop for the Sub-Agent."""
        self._emit(Event.INFO, f"正在调研: {self.sub_task[:30]}...", name="Sub-Task Start")
        log.info(f"SubAgent starting task: {self.sub_task}")

        loop_count = 0

        while loop_count < self.max_loops:
            # Check for stop signal
            if self.stop_event and self.stop_event.is_set():
                msg = "Received stop signal. Terminating sub-task early."
                self._emit(Event.WARN, msg)
                log.warning(msg)
                break

            loop_count += 1

            # 1. LLM Call (Reasoning)
            try:
                response = self.llm.query_json(self.message_history)
            except Exception as e:
                loop_count -= 1
                msg = f"LLM Error in SubAgent: {e}"
                self._emit(Event.ERROR, msg, name="LLM Failure")
                log.error(msg)
                # Attempt to recover by adding error message to history
                self.message_history.append(
                    {
                        "role": "user",
                        "content": f"Error occurred: {msg}. Please retry or try finishing.",
                    }
                )
                continue

            # Add assistant response to history
            self.message_history.append(
                {"role": "assistant", "content": json.dumps(response, ensure_ascii=False)}
            )

            # 2. Parse Response
            thought = response.get("thought", "")
            action = response.get("action", "")
            params = response.get("parameters", {})

            # Log Thought
            self._emit(Event.THOUGHT, thought, name="Reasoning", metadata={"step": loop_count})
            log.info(f"[SubAgent] Thought: {thought}")

            # Check for Finish
            if action == "finish":
                log.info("[SubAgent] Finished data gathering. Moving to summarization.")
                break

            # 3. Execute Tool (Act)
            result_data = self._execute_tool(action, params)

            # 4. Observe & Update History
            self.message_history.append(
                {
                    "role": "tool",
                    "content": json.dumps(
                        result_data.get("text", "")
                        if isinstance(result_data, dict) and "text" in result_data
                        else result_data,
                        ensure_ascii=False,
                    ),
                }
            )

            self._emit(
                Event.STEP,
                content={
                    "thought": thought,
                    "action": action,
                    "parameters": params,
                    "observation": result_data.get("text", "")
                    if isinstance(result_data, dict) and "text" in result_data
                    else str(result_data),
                },
                name=f"Step {loop_count}",
                metadata={"step": loop_count},
            )

            self._manage_context()

        # Fallback if loop limit reached
        if loop_count >= self.max_loops:
            fallback_msg = "Reached maximum steps for sub-task without finishing."
            self._emit(Event.WARN, fallback_msg)
            log.warning(fallback_msg)

        # Separate summarization step
        return self._summarize()

    def _summarize(self) -> str:
        """Synthesize the findings gathered in the sub-agent's loop."""
        self._emit(Event.INFO, "正在总结调研结果...", name="Summarizing")
        log.info("[SubAgent] Generating summary report...")

        history = self.message_history[1:]

        history.insert(
            0,
            {
                "role": "system",
                "content": SUB_AGENT_SUMMARIZE_PROMPT.format(sub_task=self.sub_task),
            },
        )

        try:
            summary = self.llm.query(history)
            self._emit(Event.INFO, summary, name="SubAgent Summary Completed")
            log.info("[SubAgent] Summary generated successfully.")
            return summary
        except Exception as e:
            error_msg = f"Failed to generate summary: {e}"
            self._emit(Event.ERROR, error_msg, name="Summarization Error")
            log.error(f"[SubAgent] {error_msg}")
            return (
                f"Error during summarization: {e}\nRaw history:\n{json.dumps(self.message_history)}"
            )

    def _execute_tool(self, action: str, params: dict[str, Any]) -> dict:
        """Executes the tool and logs the result."""
        try:
            self._emit(Event.ACTION, params, name=action)

            start_time = datetime.now()
            result = self.tool_registry.execute(action, params)
            duration = (datetime.now() - start_time).total_seconds()

            self._emit(Event.OBSERVATION, result, name=action, metadata={"duration": duration})

            return result
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            self._emit(Event.ERROR, error_msg, name=action)
            log.error(f"[SubAgent] {error_msg}")
            return {"type": "text", "text": error_msg}

    def _manage_context(self):
        """
        Context Management:
        If the current context size approaches the model's limit,
        compress history while keeping essential messages.
        """
        history_str = json.dumps(self.message_history)
        token_count = self.llm.count_tokens(history_str)
        limit = self.llm.get_context_limit()
        threshold = int(limit * 0.8)

        if token_count > threshold:
            self._emit(
                Event.INFO,
                f"Context size ({token_count} tokens) exceeds threshold ({threshold}). Compressing...",
            )
            log.info(f"[SubAgent] Compressing context ({token_count} > {threshold})")

            system_and_goal = self.message_history[:2]
            recent_messages = self.message_history[-4:]
            to_summarize = self.message_history[2:-4]

            summary_prompt = f"""
            Please summarize the following research steps into a concise summary.
            Focus on the key findings and actions taken so far.

            RESEARCH LOG:
            {json.dumps(to_summarize, indent=2)}
            """

            try:
                summary = self.llm.query(summary_prompt)

                new_history = system_and_goal
                new_history.append(
                    {"role": "user", "content": f"Summary of previous steps: {summary}"}
                )
                new_history.extend(recent_messages)

                self.message_history = new_history
                self._emit(Event.INFO, "Context compressed successfully.")
            except Exception as e:
                self._emit(Event.ERROR, f"Context compression failed: {e}")
                log.error(f"[SubAgent] Context compression failed: {e}")
