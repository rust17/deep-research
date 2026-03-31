import threading
from typing import Any

from ..log import log
from ..sub_agent import SubAgent
from ..validator import ValidatorAgent
from ..stream_handler import StreamHandler


def delegate_task(
    sub_task: str,
    stream_handler: StreamHandler = None,
    stop_event: threading.Event = None,
    validator: ValidatorAgent = None,
) -> dict:
    """
    Delegate a specific sub-task to a Worker Sub-Agent.
    """
    log.info(f"MainAgent delegating task: {sub_task}")

    try:
        # 1. Run SubAgent
        sub_agent = SubAgent(
            sub_task=sub_task,
            max_loops=10,
            stream_handler=stream_handler,
            stop_event=stop_event,
        )
        summary_report = sub_agent.run()

        # If no validator is provided, return the summary report directly
        if not validator:
            return {"text": summary_report}

        # 2. Validate Result
        # Note: In the original orchestrator.py, this was unreachable due to an early return.
        # We include it here but it will only execute if validator is passed.
        validation_result = validator.validate(sub_task, summary_report)

        if validation_result.get("is_valid"):
            return {
                "text": validation_result.get("vetted_information"),
                "metadata": validation_result,
            }
        else:
            return {
                "text": f"Validation Failed: {validation_result.get('evaluation_feedback')}",
                "metadata": validation_result,
            }
    except Exception as e:
        error_msg = f"Failed during task delegation: {e}"
        log.error(error_msg)
        return {"text": error_msg}
