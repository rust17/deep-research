import json
import threading
from datetime import datetime
from typing import Any, List, Dict

from .llm_client import LLMClient
from .prompt import ORCHESTRATOR_SYSTEM_PROMPT, REPORT_SUMMARIZE_PROMPT
from .stream_handler import Event, Pulse, StreamHandler
from .log import log
from .tool_manager import ToolRegistry


class Orchestrator:
    def __init__(
        self,
        user_goal: str,
        max_loops: int = 15,
        stream_handler: StreamHandler = None,
        stop_event: threading.Event = None,
    ):
        self.user_goal = user_goal
        self.max_loops = max_loops
        self.stream_handler = stream_handler
        self.stop_event = stop_event

        self.llm = LLMClient()
        self.tool_registry = ToolRegistry()

        # Context Management
        self.message_history: List[Dict[str, str]] = []
        self._init_history()

    def _init_history(self):
        """Initialize message history with system prompt and user goal."""
        system_content = ORCHESTRATOR_SYSTEM_PROMPT.format(
            tools_schema=json.dumps(self.tool_registry.get_tools_schema(), ensure_ascii=False)
        )

        self.message_history.append({"role": "system", "content": system_content})

        user_init_msg = (
            f"Current Date: {datetime.now().strftime('%Y-%m-%d')}\nUser Goal: {self.user_goal}"
        )
        self.message_history.append({"role": "user", "content": user_init_msg})

    def _emit(
        self, event: Event, content: Any = None, name: str = "", metadata: dict = None
    ) -> Pulse:
        pulse = Pulse(
            type=event,
            content=content,
            name=name,
            metadata=metadata or {},
        )
        if self.stream_handler:
            self.stream_handler.emit(pulse)

        # 自动同步到 Task
        if event == Event.FINISH:
            log.finish(result=content)
        else:
            # 使用 name 作为步骤标题，如果没有则使用 event 的值
            log.step(event, name or event.value, content, metadata=metadata)

        return pulse

    def run(self) -> str:
        """Main execution loop."""
        self._emit(Event.INIT, {"goal": self.user_goal})

        loop_count = 0

        while loop_count < self.max_loops:
            # Check for stop signal
            if self.stop_event and self.stop_event.is_set():
                self._emit(Event.WARN, "Received stop signal. Terminating research...")
                break

            loop_count += 1

            # 1. LLM Call (Reasoning)
            try:
                response = self.llm.query_json(self.message_history)
            except Exception as e:
                loop_count -= 1
                msg = f"LLM Error: {e}"
                self._emit(Event.ERROR, msg, name="LLM Failure")
                # Attempt to recover by adding error message to history
                self.message_history.append(
                    {
                        "role": "user",
                        "content": f"Error occurred: {msg}. Please retry or change strategy.",
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

            # Check for Finish
            if action == "finish":
                self._emit(Event.INFO, "Agent decided to finish. Synthesizing final report...")
                final_report = self._generate_final_report()
                self._emit(Event.FINISH, final_report, name="Completion")
                return final_report

            # 3. Execute Tool (Act)
            result_data = self._execute_tool(action, params)

            # 4. Observe & Update History
            self.message_history.append(
                {
                    "role": "tool",
                    "content": json.dumps(result_data.get("text", ""), ensure_ascii=False),
                }
            )

            self._emit(
                Event.STEP,
                content={
                    "thought": thought,
                    "action": action,
                    "parameters": params,
                    "observation": result_data.get("text", "")
                    if isinstance(result_data, dict)
                    else str(result_data),
                },
                name=f"Step {loop_count}",
                metadata={"step": loop_count},
            )

            self._manage_context()

        # Fallback if loop limit reached
        fallback_msg = "Reached maximum steps without a final answer."
        self._emit(Event.WARN, fallback_msg)
        final_report = self._generate_final_report()
        self._emit(Event.FINISH, final_report)
        return final_report

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

            # Keep system prompt and user goal (first 2 messages)
            # Keep the most recent 4 messages (2 tool calls and 2 results)
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
                self._emit(Event.INFO, "Compressing context...")
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

    def _generate_final_report(self) -> str:
        """Force a final synthesis based on message history."""
        # from .log import log
        # log.info(f"\n{self.message_history}\n")

        prompt = f"""
### Execution History
{self.message_history}

{REPORT_SUMMARIZE_PROMPT.format(user_goal=self.user_goal)}
"""
        return self.llm.query(prompt)
