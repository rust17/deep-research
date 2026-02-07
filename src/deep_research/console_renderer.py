from rich.panel import Panel

from .logs import console
from .stream_handler import Event, Pulse


class ConsoleRenderer:
    def __init__(self):
        self.current_step = 0

    def __call__(self, pulse: Pulse):
        self.render_pulse(pulse)

    def render_pulse(self, pulse: Pulse):
        if pulse.type == Event.INIT:
            console.rule("[bold blue]Research Initiated[/bold blue]")
            console.print(f"Goal: {pulse.content.get('goal')}")

        elif pulse.type == Event.THOUGHT:
            step = pulse.metadata.get("step", self.current_step)
            console.print(Panel(f"[bold]Thinking:[/bold] {pulse.content}", border_style="cyan"))

        elif pulse.type == Event.ACTION:
            console.info(f"Executing [bold]{pulse.name}[/bold] with: {pulse.content}")

        elif pulse.type == Event.OBSERVATION:
            result = pulse.content
            log_preview = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
            console.print(
                Panel(
                    f"[bold]Result:[/bold] {log_preview}",
                    border_style="green",
                    title=f"Output: {pulse.name}",
                )
            )

        elif pulse.type == Event.STEP:
            self.current_step = pulse.metadata.get("step", self.current_step)
            console.rule(f"[bold yellow]Step {self.current_step} Complete[/bold yellow]")

        elif pulse.type == Event.INFO:
            console.info(pulse.content)

        elif pulse.type == Event.WARN:
            console.warning(pulse.content)

        elif pulse.type == Event.ERROR:
            console.error(pulse.content)

        elif pulse.type == Event.FINISH:
            console.success("Research cycle completed.")
