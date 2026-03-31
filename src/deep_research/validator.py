from typing import Any

from .llm_client import LLMClient
from .log import log
from .prompt import VALIDATOR_SYSTEM_PROMPT


class ValidatorAgent:
    def __init__(self):
        self.llm = LLMClient()

    def validate(self, sub_task: str, summary_report: str) -> dict[str, Any]:
        """
        Validates the sub-agent's summary report.
        Returns a dict containing validation results.
        """
        log.info(f"Validator analyzing sub-task: {sub_task}")

        prompt = VALIDATOR_SYSTEM_PROMPT.format(sub_task=sub_task, summary_report=summary_report)

        try:
            response = self.llm.query_json([{"role": "user", "content": prompt}])

            # Ensure the response has the expected keys
            is_valid = response.get("is_valid", False)
            feedback = response.get("evaluation_feedback", "No feedback provided.")
            vetted_info = response.get("vetted_information", "No vetted information provided.")

            if is_valid:
                log.info("Validator passed the report.")
            else:
                log.warning(f"Validator rejected the report: {feedback}")

            return {
                "is_valid": is_valid,
                "evaluation_feedback": feedback,
                "vetted_information": vetted_info,
            }
        except Exception as e:
            error_msg = f"Validator encountered an error: {str(e)}"
            log.error(error_msg)
            # In case of validation error, we return a fallback response
            return {
                "is_valid": False,
                "evaluation_feedback": error_msg,
                "vetted_information": "Failed to validate due to error.",
            }
