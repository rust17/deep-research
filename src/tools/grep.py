import os
import re
from pathlib import Path
from typing import Optional
import fnmatch


def search_file_content(
    pattern: str, path: Optional[str] = None, include: Optional[str] = None
) -> str:
    """
    Searches for a regular expression pattern within the content of files.

    Args:
        pattern (str): The regex pattern to search for.
        path (str, optional): The directory to search within. Defaults to CWD.
        include (str, optional): Glob pattern to filter files.

    Returns:
        str: Formatted matches.
    """
    try:
        search_root = Path(path).resolve() if path else Path.cwd()
        if not search_root.exists():
            return f"Error: Path '{search_root}' does not exist."

        regex = re.compile(pattern)

        matches_output = []
        total_matches = 0

        # Ignored directories
        ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}

        for root, dirs, files in os.walk(search_root):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]

            for file in files:
                if include and not fnmatch.fnmatch(file, include):
                    continue

                file_path = Path(root) / file

                # Skip binary files roughly
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    continue
                except Exception:
                    continue

                file_matches = []
                for i, line in enumerate(lines):
                    if regex.search(line):
                        # Strip newline for display
                        clean_line = line.rstrip()
                        file_matches.append(f"L{i + 1}: {clean_line}")

                if file_matches:
                    total_matches += len(file_matches)
                    rel_path = file_path.relative_to(search_root)
                    matches_output.append(f"---")
                    matches_output.append(f"File: {rel_path}")
                    matches_output.extend(file_matches)

        if total_matches == 0:
            return f'No matches found for pattern "{pattern}".'

        header = f'Found {total_matches} matches for pattern "{pattern}" in path "{search_root}"'
        if include:
            header += f' (filter: "{include}")'
        header += ":"

        return header + "\n" + "\n".join(matches_output) + "\n---"

    except Exception as e:
        return f"Error searching file content: {str(e)}"
