import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from rich.console import Console as RichConsole

from .stream_handler import Event, Pulse


class Log(RichConsole):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._current_task = None
        return cls._instance

    def info(self, message: str):
        self.print(f"[bold blue]INFO:[/bold blue] {message}")

    def error(self, message: str):
        self.print(f"[bold red]ERROR:[/bold red] {message}")

    def warning(self, message: str):
        self.print(f"[bold yellow]WARNING:[/bold yellow] {message}")

    def success(self, message: str):
        self.print(f"[bold green]SUCCESS:[/bold green] {message}")

    def step(
        self,
        event_type: Event,
        name: str,
        content: Any,
        metadata: Optional[dict] = None,
    ):
        """
        记录一个执行步骤。如果任务尚未开始，则自动创建。
        """
        if not self._current_task:
            goal = "New Task"
            if event_type == Event.INIT and isinstance(content, dict):
                goal = content.get("goal", goal)
            self._current_task = self.Task(goal)

        self._current_task.step(event_type, name, content, metadata)

    def finish(self, status: str = "success", result: Any = None):
        """
        结束当前任务并清理上下文。
        """
        if self._current_task:
            self._current_task.finish(status, result)
            self._current_task = None

    class Task:
        """
        Task 处理数据结构和持久化。
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
            # 注意：内部类可以通过全局单例 log 打印
            log.info(f"Task initialized. Log file: [bold]{self.log_file}[/bold]")
            self._save()

        def step(
            self,
            event_type: Event,
            name: str,
            content: Any,
            metadata: Optional[dict] = None,
        ):
            pulse = Pulse(
                type=event_type,
                name=name,
                content=content,
                metadata=metadata or {},
            )
            self.steps.append(pulse.to_dict())
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
                log.error(f"Failed to save log: {e}")

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
            try:
                with open(self.log_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                log.error(f"Failed to save final log: {e}")


# Global log instance
log = Log()
