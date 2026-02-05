import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

from .logs import console


class TaskLogger:
    """
    TaskLog，用于记录结构化的思维与执行过程。
    """

    def __init__(self, goal: str, log_dir: str = "tasks_log"):
        self.task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self.goal = goal
        self.log_dir = log_dir
        self.start_time = time.time()
        self.steps: list[dict[str, Any]] = []

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        self.log_file = os.path.join(log_dir, f"{self.task_id}.json")
        console.info(f"Task Logger initialized. Log file: [bold]{self.log_file}[/bold]")

        # 记录初始信息
        self.log_step("init", "Task Started", {"goal": goal})

    def log_step(self, step_type: str, step_name: str, content: Any, metadata: dict | None = None):
        """
        记录一个执行步骤。
        step_type: 'thought', 'tool_call', 'tool_result', 'system', 'error'
        """
        step = {
            "timestamp": datetime.now().isoformat(),
            "time_since_start": round(time.time() - self.start_time, 2),
            "type": step_type,
            "name": step_name,
            "content": content,
            "metadata": metadata or {},
        }
        self.steps.append(step)
        self._save()

    def _save(self):
        data = {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": "running",
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "steps": self.steps,
        }
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.error(f"Failed to save log: {e}")

    def finish(self, status: str = "success", result: Any = None):
        data = {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": status,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration": round(time.time() - self.start_time, 2),
            "final_result": result,
            "steps": self.steps,
        }
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
