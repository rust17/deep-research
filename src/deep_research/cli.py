import argparse
import os
import sys

from dotenv import load_dotenv
from rich.markdown import Markdown
from rich.panel import Panel

from .console_renderer import ConsoleRenderer
from .logs import console
from .orchestrator import Orchestrator
from .stream_handler import StreamHandler

# 加载环境变量
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Deep Research Agent CLI")
    parser.add_argument("goal", nargs="?", help="The research goal/question")
    parser.add_argument("--max-loops", type=int, default=10, help="Max research loops")

    args = parser.parse_args()

    # 检查 API Key
    if not os.getenv("OPENAI_API_KEY"):
        console.error("OPENAI_API_KEY is not set in environment or .env file.")
        console.info("Please create a .env file with OPENAI_API_KEY=sk-...")
        sys.exit(1)

    user_goal = args.goal
    if not user_goal:
        user_goal = console.input("[bold yellow]Enter your research goal:[/bold yellow] ").strip()
        if not user_goal:
            console.error("Goal cannot be empty.")
            sys.exit(1)

    console.print()
    console.rule("[bold magenta]Deep Research Agent[/bold magenta]")
    console.info(f"🚀 Starting Deep Research for: [bold cyan]{user_goal}[/bold cyan]\n")

    handler = StreamHandler()
    renderer = ConsoleRenderer()
    handler.subscribe(renderer)

    agent = Orchestrator(user_goal=user_goal, max_loops=args.max_loops, stream_handler=handler)

    try:
        final_report = agent.run()

        # Save Report
        report_path = "tasks_log/research_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(final_report)

        console.print()
        console.rule("[bold green]Research Completed[/bold green]")
        console.success(f"Report saved to [bold]{report_path}[/bold].\n")

        console.print(
            Panel(
                Markdown(final_report),
                title="[bold]Final Report[/bold]",
                border_style="green",
            )
        )

    except KeyboardInterrupt:
        console.error("Research interrupted by user.")
    except Exception as e:
        console.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
