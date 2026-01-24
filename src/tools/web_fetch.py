import re
import logging
import requests
from bs4 import BeautifulSoup
import html2text
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)

def web_fetch(prompt: str) -> str:
    """
    Processes content from URL(s) embedded in a prompt using an LLM.

    Args:
        prompt (str): A comprehensive prompt that includes the URL(s) (up to 20).

    Returns:
        str: The generated response from the LLM based on the prompt and URL content.
    """
    # 1. Extract URLs
    # Simple regex to find http/https URLs
    urls = re.findall(r'https?://[^\s,]+', prompt)

    # Remove duplicates while preserving order
    unique_urls = []
    for url in urls:
        # Strip trailing punctuation and common delimiters (quotes, parens, etc) sometimes caught by regex
        url = url.rstrip('.,;!?)]}"\'`>')
        if url not in unique_urls:
            unique_urls.append(url)

    if not unique_urls:
        return "Error: No valid URLs found in the prompt. Please provide at least one URL starting with http:// or https://."

    if len(unique_urls) > 20:
        return "Error: Too many URLs. Please provide a maximum of 20 URLs."

    logger.info(f"web_fetch: Found {len(unique_urls)} URLs to process.")

    # 2. Fetch Content
    fetched_contents = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(_fetch_url_content, url): url for url in unique_urls}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                content = future.result()
                fetched_contents.append(f"=== Content from {url} ===\n{content}\n")
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {e}")
                fetched_contents.append(f"=== Content from {url} ===\nError fetching content: {str(e)}\n")

    # 3. Process with LLM
    context_data = "\n".join(fetched_contents)

    # Construct the final prompt for the LLM
    llm_prompt = f"""
You are an intelligent assistant. The user has provided the following prompt which includes URLs.
The content of these URLs has been fetched and is provided below.

User Prompt:
{prompt}

--- FETCHED CONTENT START ---
{context_data}
--- FETCHED CONTENT END ---

Please fulfill the user's request using the provided content.
"""

    try:
        llm = LLMClient()
        response = llm.query(llm_prompt)
        return response
    except Exception as e:
        return f"Error processing request with LLM: {str(e)}"

def _fetch_url_content(url: str, timeout: int = 15) -> str:
    """
    Fetches and cleans content from a URL.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove noise
        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "svg"]):
            element.decompose()

        # Convert to Markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        h.protect_links = True

        text = h.handle(str(soup))

        # Truncate
        if len(text) > 20000:
             text = text[:20000] + "\n\n[...Content Truncated...]"

        return text
    except Exception as e:
        raise e
