import logging
import json
import time
import datetime
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.state_manager import StateManager
from src.llm_client import LLMClient
from src.tools import web_research, write_todos, web_fetch
from src.prompts import INIT_PLAN_PROMPT, DECISION_PROMPT, REPORT_PROMPT, SYNTHESIZE_PROMPT, TASK_COMPLETION_PROMPT

logger = logging.getLogger(__name__)

class ResearchAgent:
    def __init__(self, user_goal: str, max_loops: int = 10):
        self.user_goal = user_goal
        self.max_loops = max_loops
        self.state = StateManager()
        self.llm = LLMClient()
        self.loop_count = 0
        self.task_decision_history = []
        self.current_task_tracker = None
        self.console = Console()

    def initialize(self):
        """生成初始计划并设置环境"""
        self.console.rule("[bold blue]Initializing Research[/bold blue]")
        self.console.print(f"Goal: [bold green]{self.user_goal}[/bold green]")

        now = datetime.datetime.now()
        # 1. Generate Plan via LLM (JSON)
        prompt = INIT_PLAN_PROMPT.format(
            user_goal=self.user_goal,
            current_date=now.strftime("%Y-%m-%d")
        )
        plan_data = self.llm.query_json(prompt)

        # 2. Use tool todo to format plan
        # Convert list of strings to list of dicts with status
        todo_list = [
            {"description": desc}
            for desc in plan_data.get("todos", [])
        ]

        plan_markdown = write_todos(todo_list)

        # 3. Init Files
        self.state.init_files(plan_markdown)
        self.console.print(Panel(Markdown(plan_markdown), title="[bold]Initial Plan[/bold]", border_style="blue"))

    def run(self) -> str:
        """主执行循环"""
        self.initialize()

        while self.loop_count < self.max_loops:
            self.console.rule(f"[bold yellow]Loop {self.loop_count + 1}/{self.max_loops}[/bold yellow]")

            # 0. Get Current Task
            current_task = self.state.read_plan()
            if not current_task:
                self.console.print("[bold green]No more pending tasks. Research completed![/bold green]")
                break

            self.console.print(f"[bold cyan]Current Task:[/bold cyan] {current_task}")

            # Reset history if task changed
            if current_task != self.current_task_tracker:
                self.current_task_tracker = current_task
                self.task_decision_history = []

            # A. Decide Next Step (Plan + Findings)
            full_plan = self.state.get_full_plan()
            findings = self.state.read_findings()
            context = f"# Research Goal\n{self.user_goal}\n\n# Current Plan\n{full_plan}\n\n# Current Findings\n{findings}"

            decision = self._get_decision(context, current_task)
            if not decision:
                self.console.print("[bold red]Failed to get valid decision. Skipping loop.[/bold red]")
                self.loop_count += 1
                continue

            # Duplicate Decision Check
            decision_signature = json.dumps(decision, sort_keys=True)
            self.task_decision_history.append(decision_signature)

            if self.task_decision_history.count(decision_signature) > 2:
                self.console.print(f"[bold red]Decision repeated > 2 times. Forcing completion for task:[/bold red] {current_task}")
                self.state.mark_task_completed(current_task)
                self.loop_count += 1
                continue

            action = decision.get("action")
            params = decision.get("parameters", {})
            reason = params.get("reason", "No reason provided")

            self.console.print(Panel(f"[bold]Action:[/bold] {action.upper()}\n[bold]Reason:[/bold] {reason}", title="Decision", border_style="magenta"))

            if action == "finish":
                self.console.print("[bold green]Agent decided to finish.[/bold green]")
                break

            # B. Clear Progress (Buffer)
            self.state.clear_progress()

            # C. Execute Action
            with self.console.status(f"[bold]Executing {action}...[/bold]", spinner="dots"):
                result = self._execute_action(action, params)

            # Save Raw Result to Progress
            self.state.add_progress(
                action=f"{action} (Params: {str(params)})",
                result=result
            )

            # D. Synthesize Findings
            with self.console.status("[bold]Synthesizing findings...[/bold]", spinner="dots"):
                new_insight = self._synthesize_step()

            if new_insight:
                self.console.print(Panel(Markdown(new_insight), title="New Insight", border_style="green"))

            # E. Check & Mark Task Completed
            if self._check_task_completion(current_task, new_insight or findings):
                self.state.mark_task_completed(current_task)
                self.console.print(f"[bold green]Task '{current_task}' marked as COMPLETED.[/bold green]")
            else:
                self.console.print(f"[bold yellow]Task '{current_task}' still INCOMPLETE. Continuing...[/bold yellow]")

            self.loop_count += 1

        # 3. Generate Report
        return self._generate_report()

    def _get_decision(self, context: str, current_task: str) -> Dict[str, Any]:
        now = datetime.datetime.now()
        prompt = DECISION_PROMPT.format(
            context=context,
            current_task=current_task,
            current_date=now.strftime("%Y-%m-%d"),
            current_year=now.year,
            next_year=now.year + 1
        )
        try:
            return self.llm.query_json(prompt)
        except Exception as e:
            logger.error(f"Decision making failed: {e}")
            return {}

    def _check_task_completion(self, current_task: str, latest_findings: str) -> bool:
        """使用 LLM 判断任务是否完成"""
        if not latest_findings:
            return False

        now = datetime.datetime.now()
        prompt = TASK_COMPLETION_PROMPT.format(
            current_task=current_task,
            latest_findings=latest_findings,
            current_date=now.strftime("%Y-%m-%d")
        )
        try:
            result = self.llm.query_json(prompt)
            is_completed = result.get("is_completed", False)
            reason = result.get("reason", "No reason")
            logger.info(f"Task Completion Check: {is_completed} - {reason}")
            return is_completed
        except Exception as e:
            logger.error(f"Task completion check failed: {e}")
            # Default to False to be safe.
            return False

    def _execute_action(self, action: str, params: Dict[str, Any]) -> str:
        """执行具体动作并返回结果字符串"""
        try:
            if action == "web_research":
                query = params.get("query")
                max_links = params.get("max_links", 5)
                region = params.get("region", "wt-wt")
                if not query: return "Error: Missing 'query' parameter."
                return web_research(query, max_links=max_links, region=region)

            elif action == "web_fetch":
                url_prompt = params.get("url_prompt")
                if not url_prompt: return "Error: Missing 'url_prompt' parameter."
                return web_fetch(url_prompt)

            elif action == "finish":
                return "Research completed."

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return f"Exception during execution: {str(e)}"

    def _synthesize_step(self) -> str:
        """分析 Progress 并更新 Findings"""
        def _filter_progress(self, text: str, max_lines: int = 500) -> str:
                """
                参照 read_file 逻辑处理 Progress 内容：
                1. 仅保留对每行的 strip()。
                2. 如果内容过长，在顶部增加标准的截断提示。
                """
                if not text:
                    return ""

                lines = [line.strip() for line in text.split('\n')]
                total_lines = len(lines)

                if total_lines > max_lines:
                    content = "\n".join(lines[:max_lines])
                    # 参照提供的 TypeScript 模板格式
                    return f"""
        IMPORTANT: The content has been truncated.
        Status: Showing lines 1-{max_lines} of {total_lines} total lines.
        Action: To read more of the content, you can adjust the research parameters or check the raw logs.

        --- CONTENT (truncated) ---
        {content}"""

                return "\n".join(lines)

        logger.info("Synthesizing information...")

        raw_progress = self.state.read_progress()
        findings = self.state.read_findings()

        # Filter progress to remove noise
        progress = _filter_progress(self, raw_progress, 2000)

        prompt = SYNTHESIZE_PROMPT.format(
            user_goal=self.user_goal,
            existing_findings=findings,
            new_progress=progress,
            current_date=datetime.datetime.now().strftime("%Y-%m-%d")
        )

        try:
            logger.info("Synthesizing start...")
            new_insight = self.llm.query(prompt)
            logger.info("Synthesizing logging...")
            self.state.add_finding(new_insight)
            logger.info("Synthesizing Findings updated.")
            return new_insight
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return ""

    def _generate_report(self) -> str:
        logger.info("Generating final report...")
        findings = self.state.read_findings()
        prompt = REPORT_PROMPT.format(
            user_goal=self.user_goal,
            findings=findings,
            current_date=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        report = self.llm.query(prompt)

        # Save report
        with open("tasks_log/research_report.md", "w", encoding="utf-8") as f:
            f.write(report)

        return report