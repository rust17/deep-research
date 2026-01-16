import os
from pathlib import Path

def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file.

    Args:
        file_path (str): The absolute path to the file to write to.
        content (str): The content to write.

    Returns:
        str: Success message.
    """
    try:
        path = Path(file_path).resolve()

        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = "w" if path.exists() else "x"
        status_msg = "Successfully overwrote file" if path.exists() else "Successfully created and wrote to new file"

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"{status_msg}: {file_path}"

    except Exception as e:
        return f"Error writing file '{file_path}': {str(e)}"
