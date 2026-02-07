REPORT_SUMMARIZE_PROMPT = """This is a direct instruction to you (the assistant), not the result of a tool call.

We are now ending this session, and your conversation history will be deleted. You must NOT initiate any further tool use. This is your final opportunity to report *all* of the information gathered during the session.

The original task is repeated here for reference:

"{user_goal}"

Summarize the above search and browsing history. Output the FINAL RESPONSE and detailed supporting information of the task given to you.

- If you found any useful facts, data, quotes, or answers directly relevant to the original task, include them clearly and completely.
- If you reached a conclusion or answer, include it as part of the response.
- If the task could not be fully answered, do NOT make up any content. Instead, return all partially relevant findings, search results, quotes, and observations that might help solve the problem.
- If partial, conflicting, or inconclusive information was found, clearly indicate this in your response.

Your final response should be a clear, complete, and structured report.
Organize the content into logical sections with appropriate headings (Markdown format).
Do NOT include any tool call instructions, speculative filler, or vague summaries.
Focus on factual, specific, and well-organized information.
"""
