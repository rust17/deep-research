import json
from datetime import datetime

from ..core.log import log
from ..models import Event
from ..prompts.sub_agent import SUB_AGENT_SUMMARIZE_PROMPT, SUB_AGENT_SYSTEM_PROMPT
from .base import BaseReActAgent


class SubAgent(BaseReActAgent):
    def __init__(self, sub_task: str, **kwargs):
        self.sub_task = sub_task
        super().__init__(agent_name="SubAgent", **kwargs)

    def _register_tools(self):
        self.tool_registry.register_search_and_visit()

    def _init_history(self):
        system_content = SUB_AGENT_SYSTEM_PROMPT.format(
            tools_schema=json.dumps(self.tool_registry.get_tools_schema(), ensure_ascii=False)
        )
        self.message_history.append({"role": "system", "content": system_content})

        self.message_history.append(
            {
                "role": "user",
                "content": f"Current Date: {datetime.now().strftime('%Y-%m-%d')}\nYour assigned sub-task is:\n{self.sub_task}\nPlease begin your investigation.",
            }
        )

    def _on_finish(self) -> str:
        self._emit(Event.INFO, "正在总结调研结果...", name="Summarizing")
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
            return summary
        except Exception as e:
            self._emit(Event.ERROR, f"Failed to generate summary: {e}", name="Summarization Error")
            return (
                f"Error during summarization: {e}\nRaw history:\n{json.dumps(self.message_history)}"
            )
