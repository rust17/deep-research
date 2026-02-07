from rich.console import Console as RichConsole


class Console(RichConsole):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def info(self, message: str):
        self.print(f"[bold blue]INFO:[/bold blue] {message}")

    def error(self, message: str):
        self.print(f"[bold red]ERROR:[/bold red] {message}")

    def warning(self, message: str):
        self.print(f"[bold yellow]WARNING:[/bold yellow] {message}")

    def success(self, message: str):
        self.print(f"[bold green]SUCCESS:[/bold green] {message}")


# Global console instance
console = Console()
