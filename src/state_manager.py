import os
import re
from pathlib import Path
from typing import List, Optional


class StateManager:
    def __init__(self, tasks_dir: str = "tasks_log"):
        self.tasks_dir = Path(tasks_dir)
        self.plan_path = self.tasks_dir / "plan.md"
        self.findings_path = self.tasks_dir / "findings.md"
        self.progress_path = self.tasks_dir / "progress.md"
        self.ensure_directories()

    def ensure_directories(self):
        """确保 tasks 目录存在"""
        self.tasks_dir.mkdir(exist_ok=True)

    def init_files(self, initial_plan: str):
        """初始化所有状态文件"""
        self.write_plan(initial_plan)
        self.write_file(self.findings_path, "# Research Findings\n\n")
        self.write_file(self.progress_path, "# Research Progress\n\n")

    def write_file(self, path: Path, content: str):
        """写入文件（覆盖）"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def read_file(self, path: Path) -> str:
        """读取文件内容"""
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def append_to_file(self, path: Path, content: str):
        """追加内容到文件"""
        with open(path, "a", encoding="utf-8") as f:
            f.write(content + "\n")

    # --- Plan Operations ---
    def write_plan(self, plan_content: str):
        self.write_file(self.plan_path, plan_content)

    def get_full_plan(self) -> str:
        """读取完整的计划文件内容"""
        return self.read_file(self.plan_path)

    def read_plan(self) -> Optional[str]:
        """返回第一个待办任务 (Pending Task)"""
        content = self.read_file(self.plan_path)
        if not content:
            return None

        # 查找第一个未完成的任务，支持 "- [ ]" 和 "- [pending]"
        match = re.search(r"- \[(?: |pending)\] (.*)", content)
        if match:
            return match.group(1).strip()
        return None

    def mark_task_completed(self, task_text: str):
        """将指定任务标记为已完成"""
        if not task_text:
            return

        content = self.read_file(self.plan_path)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            # 检查行中是否包含任务文本
            if task_text in line:
                # 适配 [ ] -> [x]
                if "- [ ]" in line:
                    lines[i] = line.replace("- [ ]", "- [x]", 1)
                    self.write_plan("\n".join(lines))
                    return
                # 适配 [pending] -> [completed]
                elif "- [pending]" in line:
                    lines[i] = line.replace("- [pending]", "- [completed]", 1)
                    self.write_plan("\n".join(lines))
                    return

    # --- Findings Operations ---
    def update_findings(self, findings: str):
        """覆盖更新 Findings 文件"""
        self.write_file(self.findings_path, findings)

    def read_findings(self) -> str:
        return self.read_file(self.findings_path)

    # --- Progress Operations ---
    def clear_progress(self):
        """清空进度文件内容"""
        self.write_file(self.progress_path, "# Research Progress (Cleared)\n\n")

    def add_progress(self, action: str, result: str):
        entry = f"## Action: {action}\nResult: {result}\n---\n"
        self.append_to_file(self.progress_path, entry)

    def read_progress(self) -> str:
        return self.read_file(self.progress_path)

    def get_context(self, user_goal: str) -> str:
        """组合当前的所有上下文信息供 LLM 决策"""
        plan = self.get_full_plan()
        findings = self.read_findings()
        progress = self.read_progress()

        # 为了节省 Token，Findings 和 Progress 可能只需要最近的一部分，
        # 但这里作为 Deep Research，Findings 全文可能很重要。
        # 暂时全量返回。

        context = f"""
# Research Goal
{user_goal}

# Current Plan
{plan}

# Key Findings So Far
{findings}

# Execution History (Progress)
{progress}
"""
        return context
