import argparse
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from .agent import ResearchAgent

# 加载环境变量
load_dotenv()

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Deep Research Agent CLI")
    parser.add_argument("goal", nargs="?", help="The research goal/question")
    parser.add_argument("--max-loops", type=int, default=10, help="Max research loops")

    args = parser.parse_args()

    # 检查 API Key
    if not os.getenv("OPENAI_API_KEY"):
        console.print(
            "[bold red]Error:[/bold red] OPENAI_API_KEY is not set in environment or .env file."
        )
        console.print("Please create a .env file with OPENAI_API_KEY=sk-...")
        sys.exit(1)

    user_goal = args.goal
    if not user_goal:
        user_goal = console.input("[bold yellow]Enter your research goal:[/bold yellow] ").strip()
        if not user_goal:
            console.print("[bold red]Goal cannot be empty.[/bold red]")
            sys.exit(1)

    console.print()
    console.rule("[bold magenta]Deep Research Agent[/bold magenta]")
    console.print(f"🚀 Starting Deep Research for: [bold cyan]{user_goal}[/bold cyan]\n")

    agent = ResearchAgent(user_goal=user_goal, max_loops=args.max_loops)

    try:
        final_report = agent.run()
        console.print()
        console.rule("[bold green]Research Completed[/bold green]")
        console.print(f"✅ Report saved to [bold]tasks_log/research_report.md[/bold].\n")

        console.print(
            Panel(
                Markdown(final_report),
                title="[bold]Final Report Preview[/bold]",
                border_style="green",
            )
        )

    except KeyboardInterrupt:
        console.print("\n[bold red]Research interrupted by user.[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]❌ An error occurred:[/bold red] {e}")


if __name__ == "__main__":
    main()
