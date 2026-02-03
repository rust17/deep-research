import os
import fnmatch
from pathlib import Path
from typing import List, Optional


def list_directory(
    path: str, ignore: Optional[List[str]] = None, respect_git_ignore: bool = True
) -> str:
    """
    Lists the names of files and subdirectories directly within a specified directory path.
    Can optionally ignore entries matching provided glob patterns.

    Args:
        path (str): The absolute path to the directory to list.
        ignore (List[str], optional): A list of glob patterns to exclude from the listing.
        respect_git_ignore (bool, optional): Whether to respect .gitignore patterns. Defaults to True.

    Returns:
        str: A formatted string listing the directory contents.
    """
    try:
        dir_path = Path(path).resolve()
        if not dir_path.is_dir():
            return f"Error: '{path}' is not a directory."

        # Collect ignore patterns
        ignore_patterns = set(ignore) if ignore else set()
        if respect_git_ignore:
            # Simple .gitignore parsing (only looks at the root of the listed dir if present)
            # A full implementation would traverse up directories, but this is a simplified version
            gitignore_path = dir_path / ".gitignore"
            if gitignore_path.exists():
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            ignore_patterns.add(line)

            # Also check for project root .gitignore if we are deep inside
            # For simplicity, let's just check the current directory for now,
            # or maybe the user's CWD if it's a git repo.
            # Given the constraints, let's stick to the directory's own .gitignore
            # and maybe standard defaults.
            ignore_patterns.add(".git")
            ignore_patterns.add("__pycache__")
            ignore_patterns.add(".DS_Store")

        entries = []
        for entry in os.scandir(dir_path):
            name = entry.name

            # Check ignore patterns
            should_ignore = False
            for pattern in ignore_patterns:
                if fnmatch.fnmatch(name, pattern):
                    should_ignore = True
                    break
            if should_ignore:
                continue

            entries.append(entry)

        # Sort: Directories first, then alphabetically
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

        output_lines = [f"Directory listing for {dir_path}:"]
        for entry in entries:
            prefix = "[DIR] " if entry.is_dir() else ""
            output_lines.append(f"{prefix}{entry.name}")

        return "\n".join(output_lines)

    except Exception as e:
        return f"Error listing directory '{path}': {str(e)}"
