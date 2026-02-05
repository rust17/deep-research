from rich.panel import Panel

from .logs import console
from .stream_handler import Event, EventType


class ConsoleRenderer:
    def __init__(self):
        self.current_step = 0
        self._status = None

    def __call__(self, event: Event):
        self.render_event(event)

    def render_event(self, event: Event):
        if event.type == EventType.WORKFLOW_START:
            console.rule("[bold blue]Orchestrator Started[/bold blue]")
            console.print(f"Goal: {event.data.get('goal')}")

        elif event.type == EventType.AGENT_THINK:
            step = event.data.get("step", 0)
            if step > self.current_step:
                self.current_step = step
                console.rule(f"[bold yellow]Step {self.current_step}[/bold yellow]")

            thought = event.data.get("thought", "")
            console.print(Panel(f"[bold]Thinking:[/bold] {thought}", border_style="cyan"))

        elif event.type == EventType.TOOL_START:
            action = event.data.get("tool")
            params = event.data.get("parameters")
            console.info(f"Executing {action} with parameters: {params}")
            # Note: console.status is tricky here because it's a context manager.
            # In a real event-driven system, we might use rich.live or just print.
            # For simplicity, we'll just use print for now.

        elif event.type == EventType.TOOL_END:
            action = event.data.get("tool")
            status = event.data.get("status")
            if status == "success":
                result = event.data.get("result")
                log_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
                console.print(
                    Panel(
                        f"[bold]Result:[/bold] {log_preview}",
                        border_style="green",
                        title=f"Output: {action}",
                    )
                )
            else:
                console.error(f"Tool {action} failed: {event.data.get('error')}")

        elif event.type == EventType.INFO:
            console.info(event.data.get("message"))

        elif event.type == EventType.WARNING:
            console.warning(event.data.get("message"))

        elif event.type == EventType.ERROR:
            console.error(event.data.get("message"))

        elif event.type == EventType.WORKFLOW_END:
            console.success("Orchestrator finished.")
