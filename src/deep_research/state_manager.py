from pathlib import Path


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

    def init_files(self):
        """初始化所有状态文件"""
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
