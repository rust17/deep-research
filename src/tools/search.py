import logging
from src.llm_client import LLMClient

# Deferred import to avoid circular dependency
# from src.tools import web_research

logger = logging.getLogger(__name__)

def google_web_search(query: str) -> str:
    """
    Performs a web search and returns a generated summary with sources.

    Args:
        query (str): The search query.

    Returns:
        str: A summary of the search results with citations.
    """
    try:
        # Import here to avoid circular dependency with __init__.py
        from src.tools import web_research

        logger.info(f"google_web_search: Searching for '{query}'...")

        # Use web_research to get raw content (search + fetch)
        # Limiting to 3 links for speed and conciseness as this is a quick search tool
        raw_results = web_research(query, max_links=3)

        if "Search returned no results" in raw_results or "Search failed" in raw_results:
            return raw_results

        # Summarize with LLM
        llm = LLMClient()
        prompt = f"""
You are a helpful assistant acting as a search engine interface.
The user has searched for: "{query}"

Below are the raw search results and content from the top websites found:

{raw_results}

Based ONLY on the above results:
1. Provide a concise summary answering the user's query.
2. Cite your sources using the format [Source Title](URL) or simply [Source X].
3. If the results do not contain the answer, state that clearly.
"""
        logger.info("google_web_search: Generating summary...")
        response = llm.query(prompt)
        return response

    except Exception as e:
        logger.error(f"google_web_search failed: {e}")
        return f"Error performing web search: {str(e)}"
