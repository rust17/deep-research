import logging
import json
import time
import datetime
from typing import Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.state_manager import StateManager
from src.llm_client import LLMClient
from src.tools import web_search, write_todos
from src.prompts import (
    DECISION_PROMPT,
    REPORT_PROMPT,
    SYNTHESIZE_PROMPT,
    SELECT_TASK_PROMPT
)

logger = logging.getLogger(__name__)

class ResearchAgent:
    def __init__(self, user_goal: str, max_loops: int = 10):
        self.user_goal = user_goal
        self.max_loops = max_loops
        self.state = StateManager()
        self.llm = LLMClient()
        self.loop_count = 0
        self.console = Console()
        self.search_queries = []

    def initialize(self):
        """生成初始计划并设置环境"""
        self.console.rule("[bold blue]Initializing Research[/bold blue]")
        self.console.print(f"Goal: [bold green]{self.user_goal}[/bold green]")

        # 4. Init Files (with empty plan)
        self.state.init_files("")
        self.console.print("[dim]State initialized.[/dim]")

    def run(self) -> str:
        """主执行循环"""
        self.initialize()

        while self.loop_count < self.max_loops:
            self.console.rule(f"[bold yellow]Loop {self.loop_count + 1}/{self.max_loops}[/bold yellow]")

            # 0. Get Current Task
            with self.console.status("[bold]Selecting next task...[/bold]", spinner="dots"):
                current_task = self._select_next_task()

            if not current_task:
                self.console.print("[bold green]No more pending tasks. Research completed![/bold green]")
                break

            self.console.print(f"[bold cyan]Current Task:[/bold cyan] {current_task}")

            # --- Phase 1: Research Loop (Gathering) ---
            self._research_loop(current_task)

            # --- Phase 2: Synthesize Stage (Thinking) ---
            self._synthesize_stage(current_task)

            self.loop_count += 1

        # 3. Generate Report
        return self._generate_report()

    def _research_loop(self, current_task: str):
        """循环收集信息，直到 Agent 决定开始分析"""
        research_steps = 0
        max_steps = 5  # 防止无限搜索

        while research_steps < max_steps:
            progress = self.state.read_progress() # Current buffer

            context = f"# Research Goal\n{self.user_goal}\n\n# Gathered Info (Buffer)\n{progress}"

            decision = self._get_decision(context, current_task)
            if not decision:
                self.console.print("[bold red]Failed to get valid decision. Breaking research loop.[/bold red]")
                break

            action = decision.get("action")
            params = decision.get("parameters", {})
            reason = params.get("reason", "No reason provided")

            self.console.print(Panel(f"[bold]Action:[/bold] {action.upper()}\n[bold]Reason:[/bold] {reason}", title="Decision", border_style="magenta"))

            if action == "analyze":
                self.console.print("[bold green]Agent decided to analyze collected info.[/bold green]")
                break

            # Execute & Buffer
            with self.console.status(f"[bold]Executing {action}...[/bold]", spinner="dots"):
                result = self._execute_action(action, params)

            self.state.add_progress(
                action=f"{action} (Params: {str(params)})",
                result=result
            )
            research_steps += 1

        if research_steps >= max_steps:
            self.console.print("[bold yellow]Max research steps reached. Forcing synthesis.[/bold yellow]")

    def _synthesize_stage(self, current_task: str):
        """处理信息，更新发现，调整计划，检查完成"""

        # 1. Synthesize Findings
        with self.console.status("[bold]Synthesizing findings...[/bold]", spinner="dots"):
            new_insight = self._synthesize_step()

        if new_insight:
            self.console.print(Panel(Markdown(new_insight), title="New Insight", border_style="green"))

        # 2. Clear Progress Buffer (After synthesis is done)
        self.state.clear_progress()

    def _select_next_task(self) -> Optional[str]:
        """LLM Selects the next most important task"""
        # current_plan = self.state.get_full_plan() # Plan is deprecated
        findings = self.state.read_findings()
        now = datetime.datetime.now()

        # Format past queries
        past_queries_str = "\n".join([f"- {q}" for q in self.search_queries]) if self.search_queries else "None"

        prompt = SELECT_TASK_PROMPT.format(
            user_goal=self.user_goal,
            findings=findings,
            current_date=now.strftime("%Y-%m-%d"),
            past_search_queries=past_queries_str
        )

        try:
            decision = self.llm.query_json(prompt)
            search_query = decision.get("search_query")
            reasoning = decision.get("reasoning")

            if reasoning:
                self.console.print(Panel(f"[bold]Reasoning:[/bold] {reasoning}", title="Task Selection", border_style="cyan"))

            if not search_query or "[FINISH]" in search_query.upper():
                return None

            return search_query
        except Exception as e:
            logger.error(f"Task selection failed: {e}")
            return None

    def _get_decision(self, context: str, current_task: str) -> Dict[str, Any]:
        now = datetime.datetime.now()
        prompt = DECISION_PROMPT.format(
            context=context,
            current_task=current_task,
            current_date=now.strftime("%Y-%m-%d"),
        )
        try:
            return self.llm.query_json(prompt)
        except Exception as e:
            logger.error(f"Decision making failed: {e}")
            return {}


    def _execute_action(self, action: str, params: Dict[str, Any]) -> str:
        """执行具体动作并返回结果字符串"""
        try:
            if action == "web_search":
                query = params.get("query")
                max_links = params.get("max_links", 10)
                region = params.get("region", "wt-wt")
                if not query: return "Error: Missing 'query' parameter."

                # Record the query
                self.search_queries.append(query)

                return web_search(query, max_links=max_links, region=region)

            # 'analyze' is handled in the loop, 'finish' is removed from decision

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return f"Exception during execution: {str(e)}"

    def _synthesize_step(self) -> str:
        """分析 Progress 并更新 Findings"""
        logger.info("Synthesizing information...")

        raw_progress = self.state.read_progress()
        findings = self.state.read_findings()

        # If buffer is empty, skip
        if not raw_progress:
            logger.info("No new progress to synthesize.")
            return ""

        # Progress is now summarized by the search tool, so we treat it as processed content.
        # We still keep the raw string, but semantically it is "Processed Progress".
        progress = raw_progress

        prompt = SYNTHESIZE_PROMPT.format(
            user_goal=self.user_goal,
            existing_findings=findings,
            new_progress=progress,
            current_date=datetime.datetime.now().strftime("%Y-%m-%d")
        )

        try:
            logger.info("Synthesizing start...")
            new_insight = self.llm.query(prompt)
            logger.info("Synthesizing completed.")

            if "No new insights." in new_insight:
                logger.info("No new insights found during synthesis.")
            else:
                self.state.update_findings(new_insight)
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
