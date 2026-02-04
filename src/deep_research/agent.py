from datetime import datetime
from typing import Dict, Any, Optional
from rich.panel import Panel
from rich.markdown import Markdown

from .state_manager import StateManager
from .llm_client import LLMClient
from .tools import web_search
from .prompts import DECISION_PROMPT, REPORT_PROMPT, SYNTHESIZE_PROMPT, SELECT_TASK_PROMPT
from .logs import console


class ResearchAgent:
    def __init__(self, user_goal: str, max_loops: int = 10):
        self.user_goal = user_goal
        self.max_loops = max_loops
        self.state = StateManager()
        self.llm = LLMClient()
        self.loop_count = 0
        self.console = console
        self.search_queries = []

    def initialize(self):
        """生成初始计划并设置环境"""
        self.console.rule("[bold blue]Initializing Research[/bold blue]")
        self.console.info(f"Goal: {self.user_goal}")

        # 4. Init Files (with empty plan)
        self.state.init_files()
        self.console.info("State initialized.")

    def run(self) -> str:
        """主执行循环"""
        self.initialize()

        while self.loop_count < self.max_loops:
            self.console.rule(
                f"[bold yellow]Loop {self.loop_count + 1}/{self.max_loops}[/bold yellow]"
            )

            # 0. Get Current Task
            with self.console.status("[bold]Selecting next task...[/bold]", spinner="dots"):
                current_task = self._next_task()

            if not current_task:
                self.console.success("No more tasks. Research completed!")
                break

            self._research(current_task)

            self._think(current_task)

            self.loop_count += 1

        # 3. Generate Report
        return self._generate_report()

    def _research(self, current_task: str):
        """循环收集信息，直到 Agent 决定开始分析"""
        research_steps = 0
        max_steps = 5  # 防止无限搜索

        while research_steps < max_steps:
            progress = self.state.read_progress()  # Current buffer

            context = f"# Research Goal\n{self.user_goal}\n\n# Gathered Info\n{progress}"

            with self.console.status(f"[bold]Deciding...", spinner="dots"):
                decision = self._get_decision(context, current_task)

            if not decision:
                self.console.error("Failed to get valid decision. Breaking research loop.")
                break

            action = decision.get("action")
            params = decision.get("parameters", {})
            reason = params.get("reason", "No reason provided")

            self.console.print(
                Panel(
                    f"[bold]Action:[/bold] {action.upper()}\n[bold]Reason:[/bold] {reason}",
                    title="Decision",
                    border_style="magenta",
                )
            )

            if action == "analyze":
                self.console.info("Agent decided to analyze collected info.")
                break

            # Execute & Buffer
            with self.console.status(f"[bold]Executing {action}...[/bold]", spinner="dots"):
                result = self._execute_action(action, params)

            self.console.print(
                Panel(
                    Markdown(result),
                    title=f"Summary for Task: {current_task}",
                    border_style="green",
                )
            )

            self.state.add_progress(action=f"{action} (Params: {str(params)})", result=result)
            research_steps += 1

        if research_steps >= max_steps:
            self.console.warning("Max research steps reached. Forcing synthesis.")

    def _think(self, current_task: str):
        """处理信息，更新发现，调整计划，检查完成"""

        with self.console.status("[bold]Synthesizing findings...[/bold]", spinner="dots"):
            summary = self._summarizing(current_task)

        if summary:
            self.console.print(
                Panel(
                    Markdown(summary),
                    title=f"Summary for Goal: {self.user_goal} Task: {current_task}",
                    border_style="green",
                )
            )

        self.state.clear_progress()

    def _next_task(self) -> Optional[str]:
        """LLM Selects the next most important task"""

        findings = self.state.read_findings()
        now = datetime.now()

        # Format past queries
        past_queries_str = (
            "\n".join([f"- {q}" for q in self.search_queries]) if self.search_queries else "None"
        )

        prompt = SELECT_TASK_PROMPT.format(
            user_goal=self.user_goal,
            findings=findings,
            current_date=now.strftime("%Y-%m-%d"),
            past_search_queries=past_queries_str,
        )

        try:
            decision = self.llm.query_json(prompt)
            search_query = decision.get("search_query")
            reason = decision.get("reason")

            if reason:
                self.console.print(
                    Panel(
                        f"[bold]Task:[/bold] {search_query}\n[bold]Reason:[/bold] {reason}",
                        title="Task",
                        border_style="cyan",
                    )
                )

            if not search_query or "[FINISH]" in search_query.upper():
                return None

            return search_query
        except Exception as e:
            self.console.error(f"Task selection failed: {e}")
            return None

    def _get_decision(self, context: str, current_task: str) -> Dict[str, Any]:
        now = datetime.now()
        prompt = DECISION_PROMPT.format(
            context=context,
            current_task=current_task,
            current_date=now.strftime("%Y-%m-%d"),
        )
        try:
            return self.llm.query_json(prompt)
        except Exception as e:
            self.console.error(f"Decision making failed: {e}")
            return {}

    def _execute_action(self, action: str, params: Dict[str, Any]) -> str:
        """执行具体动作并返回结果字符串"""
        try:
            if action == "web_search":
                query = params.get("query")

                if not query:
                    return "Error: Missing 'query' parameter."

                self.search_queries.append(query)

                return web_search(query, region=params.get("region", "wt-wt"))

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            self.console.error(f"Action execution failed: {e}")
            return f"Exception during execution: {str(e)}"

    def _summarizing(self, current_task: str) -> str:
        """分析 Progress 并更新 Findings"""

        progress = self.state.read_progress()

        findings = self.state.read_findings()

        # If buffer is empty, skip
        if not progress:
            self.console.warning("No new progress to synthesize.")
            return ""

        prompt = SYNTHESIZE_PROMPT.format(
            user_goal=self.user_goal,
            current_task=current_task,
            existing_findings=findings,
            new_progress=progress,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )

        try:
            new_insight = self.llm.query(prompt)

            if "No new insights." in new_insight:
                self.console.info("No new insights found during synthesis.")
            else:
                self.state.update_findings(new_insight)

            return new_insight
        except Exception as e:
            self.console.error(f"Synthesis failed: {e}")
            return ""

    def _generate_report(self) -> str:
        findings = self.state.read_findings()
        prompt = REPORT_PROMPT.format(
            user_goal=self.user_goal,
            findings=findings,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )
        report = self.llm.query(prompt)

        # Save report
        with open("tasks_log/research_report.md", "w", encoding="utf-8") as f:
            f.write(report)

        return report
