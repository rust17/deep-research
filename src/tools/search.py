import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import html2text
from ddgs import DDGS
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)

def web_research(query: str, max_links: int = 5, region: str = "wt-wt") -> str:
    """
    Comprehensive research tool: Performs search and automatically visits top links.
    1. Searches for keywords.
    2. Extracts multiple candidate URLs.
    3. Concurrently visits these URLs to fetch full text.
    4. Returns consolidated content.
    """
    logger.info(f"Starting web research for: {query} (max_links={max_links}, region={region})")

    # 1. Search
    try:
        raw_results = []
        with DDGS() as ddgs:
            # Request more results than needed to filter out invalid ones
            ddgs_gen = ddgs.text(query, region=region, max_results=max_links * 2)
            if ddgs_gen:
                raw_results = list(ddgs_gen)

        if not raw_results:
            return f"Search for '{query}' returned no results."

        # Extract URLs and titles, filtering up to max_links
        targets = []
        for res in raw_results:
            if len(targets) >= max_links:
                break
            link = res.get('href')
            title = res.get('title', 'No Title')
            if link:
                targets.append({"url": link, "title": title})

        logger.info(f"Found {len(targets)} valid links to visit.")

    except Exception as e:
        logger.error(f"Search phase failed: {e}")
        return f"Search failed: {str(e)}"

    # 2. Batch Visit
    if not targets:
        return "Search returned results but no valid URLs found."

    visited_content = []
    with ThreadPoolExecutor(max_workers=max_links) as executor:
        future_to_url = {
            executor.submit(_visit_page_internal, t["url"]):
            t["title"]
            for t in targets
        }

        for future in as_completed(future_to_url):
            title = future_to_url[future]
            try:
                content = future.result()
                optimized = _optimize_content(content, query)
                visited_content.append(f"=== Source: {title} ===\n{optimized}\n")
            except Exception as exc:
                visited_content.append(f"=== Source: {title} ===\nFailed to load: {exc}\n")

    # 3. Combine Output
    final_output = f"## Research Results for: {query}\n\n"
    final_output += "\n".join(visited_content)

    return final_output

def _optimize_content(text: str, query: str, max_chars: int = 3000) -> str:
    """
    Optimizes content by:
    1. Removing lines that are just links or too short/noisy.
    2. Prioritizing paragraphs that contain query keywords.
    3. Truncating to a safe limit.
    """
    if not text:
        return ""

    lines = text.split('\n')
    unique_lines = set()
    cleaned_lines = []
    
    # 1. Basic Cleaning
    for line in lines:
        stripped = line.strip()
        # Remove duplicates
        if stripped in unique_lines:
            continue
        unique_lines.add(stripped)
        
        # Skip lines that are just links (common in navs)
        # Markdown link pattern: [text](url)
        if stripped.startswith("[") and stripped.endswith(")") and "](" in stripped:
            if len(stripped) < 100: # Short links are likely nav items
                continue
        
        cleaned_lines.append(line)

    # 2. Relevance Scoring
    # Simple strategy: Find lines with query terms
    terms = [t.lower() for t in query.split() if len(t) > 1]
    if not terms:
        terms = [query.lower()]
        
    scored_blocks = []
    current_block = []
    
    # Group into blocks (paragraphs)
    for line in cleaned_lines:
        if not line.strip():
            if current_block:
                text_block = "\n".join(current_block)
                score = sum(1 for t in terms if t in text_block.lower())
                scored_blocks.append((score, text_block))
                current_block = []
        else:
            current_block.append(line)
            
    if current_block:
        text_block = "\n".join(current_block)
        score = sum(1 for t in terms if t in text_block.lower())
        scored_blocks.append((score, text_block))

    # 3. Select Top Blocks
    # Sort by score desc, then by original position (implicitly via sort stability if needed, but here we prioritize score)
    # To keep flow, we might want to keep order, but for "Research" finding the needle is more important.
    scored_blocks.sort(key=lambda x: x[0], reverse=True)
    
    selected_text = []
    current_len = 0
    
    # Always keep the top scoring blocks until limit
    for score, block in scored_blocks:
        if current_len + len(block) > max_chars:
            if current_len == 0: # At least one block
                selected_text.append(block[:max_chars])
            break
        
        selected_text.append(block)
        current_len += len(block)
        
        # If we have enough "good" content (score > 0), stop early to avoid filling with junk
        # But if scores are 0 (no match), we effectively return random parts (top of list), 
        # so maybe we should just fallback to original top text if no matches found.
    
    if not selected_text:
        # Fallback: Just return start of text
        return "\n".join(cleaned_lines)[:max_chars]

    return "\n\n".join(selected_text)

def web_search(query: str, max_links: int = 3, region: str = "wt-wt") -> str:
    """
    Performs a web search and returns a generated summary with sources.
    Uses web_research to get content, then summarizes it.

    Args:
        query (str): The search query.
        max_links (int): Number of links to visit.
        region (str): Search region.

    Returns:
        str: A summary of the search results with citations.
    """
    try:
        logger.info(f"web_search: Searching for '{query}'...")

        # Use web_research to get raw content (search + fetch)
        raw_results = web_research(query, max_links=max_links, region=region)

        if "Search returned no results" in raw_results or "Search failed" in raw_results:
            return raw_results

        # Summarize with LLM
        llm = LLMClient()
        prompt = f"""
你是一个专业的搜索助手。
用户搜索的关键词是："{query}"

以下是从网页抓取到的原始搜索结果和内容：

{raw_results}

请严格基于上述搜索结果：
1. 提供一个简洁、准确的摘要来回答用户的问题。
2. 引用来源，格式为 [来源标题](URL) 或直接使用 [来源序号]。
3. 如果搜索结果中不包含答案，请明确告知用户。
"""
        logger.info("web_search: Generating summary...")
        response = llm.query(prompt)
        return response

    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return f"Error performing web search: {str(e)}"

def _visit_page_internal(url: str, timeout: int = 15) -> str:
    """
    Internal function to visit a single page and extract text.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        # Fix encoding issues by letting requests guess based on content
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')

        # Clean up
        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "svg"]):
            element.decompose()

        # Convert to Markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        h.protect_links = True

        text = h.handle(str(soup))

        # Add Source URL marker
        text = f"URL: {url}\n\n{text}"

        # Truncate
        if len(text) > 15000:
            text = text[:15000] + "\n\n[...Content Truncated...]"

        return text

    except Exception as e:
        # logger.warning(f"Failed to visit {url}: {e}") # Reduce noise
        raise e