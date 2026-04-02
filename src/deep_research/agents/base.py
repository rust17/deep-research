import json
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..core.llm_client import LLMClient
from ..core.log import log
from ..core.stream_handler import StreamHandler
from ..models import Event, Pulse
from ..tools.manager import ToolRegistry


class BaseReActAgent(ABC):
    def __init__(
        self,
        max_loops: int = 15,
        stream_handler: StreamHandler = None,
        stop_event: threading.Event = None,
        agent_name: str = "Agent",
    ):
        self.max_loops = max_loops
        self.stream_handler = stream_handler
        self.stop_event = stop_event
        self.agent_name = agent_name

        self.llm = LLMClient()
        self.tool_registry = ToolRegistry()
        self.message_history: list[dict[str, str]] = []

        self._register_tools()
        self._init_history()

    @abstractmethod
    def _register_tools(self):
        """Register tools specific to the agent."""
        pass

    @abstractmethod
    def _init_history(self):
        """Initialize message history with system prompt and task."""
        pass

    @abstractmethod
    def _on_finish(self) -> str:
        """Logic to execute when the agent decides to finish."""
        pass

    def _emit(
        self, event: Event, content: Any = None, name: str = "", metadata: dict = None
    ) -> None:
        if self.stream_handler:
            self.stream_handler.emit(
                Pulse(
                    type=event,
                    content=content,
                    name=f"[{self.agent_name}] {name}" if self.agent_name else name,
                    metadata=metadata or {},
                )
            )

        # Sync to Log
        if event == Event.FINISH:
            log.finish(result=content)
        else:
            log.step(event, name or event.value, content, metadata=metadata)

    def run(self) -> str:
        """Main execution loop (ReAct)."""
        loop_count = 0

        while loop_count < self.max_loops:
            if self.stop_event and self.stop_event.is_set():
                self._emit(Event.WARN, "Received stop signal. Terminating early...")
                break

            loop_count += 1

            # 1. Reasoning
            try:
                response = self.llm.query_json(self.message_history)
            except Exception as e:
                loop_count -= 1
                msg = f"LLM Error: {e}"
                self._emit(Event.ERROR, msg, name="LLM Failure")
                self.message_history.append(
                    {
                        "role": "user",
                        "content": f"Error occurred: {msg}. Please retry or change strategy.",
                    }
                )
                continue

            self.message_history.append(
                {"role": "assistant", "content": json.dumps(response, ensure_ascii=False)}
            )

            thought = response.get("thought", "")
            action = response.get("action", "")
            params = response.get("parameters", {})

            self._emit(Event.THOUGHT, thought, name="Reasoning", metadata={"step": loop_count})

            if action == "finish":
                return self._on_finish()

            # 2. Act
            result_data = self._execute_tool(action, params)

            # 3. Observe
            obs_content = (
                result_data.get("text", "")
                if isinstance(result_data, dict) and "text" in result_data
                else str(result_data)
            )
            self.message_history.append(
                {
                    "role": "tool",
                    "content": json.dumps(obs_content, ensure_ascii=False),
                }
            )

            self._emit(
                Event.STEP,
                content={
                    "thought": thought,
                    "action": action,
                    "parameters": params,
                    "observation": obs_content,
                },
                name=f"Step {loop_count}",
                metadata={"step": loop_count},
            )

            self._manage_context()

        # Fallback if loop limit reached
        self._emit(Event.WARN, "Reached maximum steps without a final answer.")
        return self._on_finish()

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
        """Context Management with compression."""
        history_str = json.dumps(self.message_history)
        token_count = self.llm.count_tokens(history_str)
        limit = self.llm.get_context_limit()
        threshold = int(limit * 0.8)

        if token_count > threshold:
            self._emit(
                Event.INFO,
                f"Context size ({token_count} tokens) exceeds threshold. Compressing...",
            )

            system_and_goal = self.message_history[:2]
            recent_messages = self.message_history[-4:]
            to_summarize = self.message_history[2:-4]

            summary_prompt = f"Please summarize the following research steps concisely:\n{json.dumps(to_summarize, indent=2)}"

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
