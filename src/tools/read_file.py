import base64
import mimetypes
from pathlib import Path
from typing import Optional, Union, Dict

def read_file(path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> Union[str, Dict]:
    """
    Reads and returns the content of a specified file. Handles text and specific binary formats.

    Args:
        path (str): The absolute path to the file to read.
        offset (int, optional): Start line number (0-based) for text files.
        limit (int, optional): Maximum number of lines to read for text files.

    Returns:
        Union[str, Dict]: File content as string (text) or object with inlineData (binary).
    """
    try:
        file_path = Path(path).resolve()
        if not file_path.exists():
            return f"Error: File '{path}' does not exist."
        if not file_path.is_file():
            return f"Error: '{path}' is not a file."

        # Guess mime type
        mime_type, _ = mimetypes.guess_type(file_path)

        # Binary types to support
        supported_binary_mimes = [
            'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/svg+xml', 'image/bmp',
            'audio/mpeg', 'audio/wav', 'audio/x-aiff', 'audio/aac', 'audio/ogg', 'audio/flac',
            'application/pdf'
        ]

        is_binary = False
        if mime_type and any(mime_type.startswith(t.split('/')[0]) for t in supported_binary_mimes):
             # Simplified check, strictly checking against list for safety or prefixes
             if mime_type in supported_binary_mimes:
                 is_binary = True

        # Fallback: check if it looks like binary by reading a chunk
        if not is_binary:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(1024)
            except UnicodeDecodeError:
                is_binary = True
                # Set a generic binary mime type if not guessed
                if not mime_type:
                    mime_type = 'application/octet-stream'

        if is_binary:
            if mime_type in supported_binary_mimes:
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode('utf-8')
                return {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": data
                    }
                }
            else:
                return f"Cannot display content of binary file: {path}"

        # Text File Handling
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
             return f"Error reading text file: {str(e)}"

        total_lines = len(lines)

        # Default limit if not set
        if limit is None:
            limit = 2000

        start_index = offset if offset is not None else 0
        end_index = start_index + limit

        truncated_lines = lines[start_index:end_index]
        content = "".join(truncated_lines)

        if total_lines > limit or start_index > 0:
            header = f"[File content truncated: showing lines {start_index+1}-{min(end_index, total_lines)} of {total_lines} total lines...]\n"
            return header + content

        return content

    except Exception as e:
        return f"Error reading file '{path}': {str(e)}"
