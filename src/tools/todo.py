from typing import List, Dict

def write_todos(todos: List[Dict[str, str]]) -> str:
    """
    Creates and manages a list of subtasks for complex user requests.

    Args:
        todos (List[Dict[str, str]]): The complete list of todo items.
            Each item includes:
            - 'description' (str): The task description.
            - 'status' (str): The current status ('pending', 'in_progress', 'completed', or 'cancelled').

    Returns:
        str: A summary of the updated todo list.
    """
    if not isinstance(todos, list):
        return "Error: 'todos' must be a list of objects."

    summary = []
    for todo in todos:
        desc = todo.get("description", "No description")
        status = todo.get("status", "pending")
        summary.append(f"- [{status}] {desc}")

    return "\n".join(summary)

