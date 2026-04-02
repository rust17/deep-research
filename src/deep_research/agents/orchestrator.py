import json
from datetime import datetime

from ..models import Event
from ..prompts.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT, REPORT_SUMMARIZE_PROMPT
from .base import BaseReActAgent


class Orchestrator(BaseReActAgent):
    def __init__(self, user_goal: str, **kwargs):
        self.user_goal = user_goal
        super().__init__(agent_name="Orchestrator", **kwargs)

    def _register_tools(self):
        self.tool_registry.register_delegate_task(
            stream_handler=self.stream_handler,
            stop_event=self.stop_event,
        )

    def _init_history(self):
        system_content = ORCHESTRATOR_SYSTEM_PROMPT.format(
            tools_schema=json.dumps(self.tool_registry.get_tools_schema(), ensure_ascii=False)
        )
        self.message_history.append({"role": "system", "content": system_content})

        user_init_msg = (
            f"Current Date: {datetime.now().strftime('%Y-%m-%d')}\nUser Goal: {self.user_goal}"
        )
        self.message_history.append({"role": "user", "content": user_init_msg})

    def _on_finish(self) -> str:
        self._emit(Event.INFO, "Agent decided to finish. Synthesizing final report...")
        prompt: list[dict[str, str]] = [
            {"role": "system", "content": REPORT_SUMMARIZE_PROMPT.format(user_goal=self.user_goal)},
            {
                "role": "user",
                "content": f"### Execution History\n{self.message_history[1:]}",
            },
        ]
        final_report = self.llm.query(prompt)
        self._emit(Event.FINISH, final_report, name="Completion")
        return final_report
