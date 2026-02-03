import os
from pathlib import Path


def replace(
    file_path: str, old_string: str, new_string: str, expected_replacements: int = 1
) -> str:
    """
    Replaces text within a file.

    Args:
        file_path (str): The absolute path to the file.
        old_string (str): The exact text to replace. If empty, creates new file.
        new_string (str): The new text.
        expected_replacements (int): Number of expected replacements.

    Returns:
        str: Success or error message.
    """
    try:
        path = Path(file_path).resolve()

        # Case 1: Create new file
        if not old_string:
            if path.exists():
                return f"Error: 'old_string' is empty but file '{file_path}' already exists."

            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_string)
            return f"Created new file: {file_path} with provided content."

        # Case 2: Modify existing file
        if not path.exists():
            return f"Error: File '{file_path}' does not exist."

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_string)

        if count == 0:
            return f"Failed to edit: 'old_string' not found in '{file_path}'."

        if count != expected_replacements:
            return f"Failed to edit: Expected {expected_replacements} occurrences of 'old_string', but found {count}."

        new_content = content.replace(old_string, new_string)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully modified file: {file_path} ({count} replacements)."

    except Exception as e:
        return f"Error replacing text in '{file_path}': {str(e)}"
