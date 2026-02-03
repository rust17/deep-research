import logging
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import trafilatura
from ddgs import DDGS
from ..llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result item."""

    title: str
    url: str
    snippet: Optional[str] = None


@dataclass
class CrawledPage:
    """Represents the content extracted from a visited page."""

    source: SearchResult
    content: str
    success: bool
    error: Optional[str] = None

    def to_string(self) -> str:
        """Formats the page content for display/LLM consumption."""
        header = f"=== Source: {self.source.title} ==="
        if not self.success:
            return f"{header}\nURL: {self.source.url}\nFailed to load: {self.error}\n"

        return f"{header}\nURL: {self.source.url}\n\n{self.content}\n"


class WebResearcher:
    """
    Encapsulates web research logic, session management, and concurrency.
    """

    def __init__(self, timeout: int = 15, region: str = "wt-wt"):
        self.timeout = timeout
        self.region = region
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """Performs the search using DuckDuckGo."""
        results = []
        try:
            with DDGS() as ddgs:
                # Fetching a few more to filter invalid ones, though here we trust DDGS mostly
                ddgs_gen = ddgs.text(
                    query, region=self.region, safesearch="on", max_results=max_results
                )
                if ddgs_gen:
                    for res in ddgs_gen:
                        link = res.get("href")
                        title = res.get("title", "No Title")
                        body = res.get("body", "")
                        if link:
                            results.append(SearchResult(title=title, url=link, snippet=body))

            logger.info(f"Found {len(results)} valid links for query: {query}")
            return results
        except Exception as e:
            logger.error(f"Search phase failed: {e}")
            return []

    def _visit_page(self, result: SearchResult) -> CrawledPage:
        """Internal method to fetch and extract content from a single URL."""
        try:
            response = self.session.get(result.url, timeout=self.timeout)
            response.raise_for_status()

            # Handle encoding
            if response.encoding is None:
                response.encoding = response.apparent_encoding

            # Extract text
            text = trafilatura.extract(
                response.text,
                include_links=True,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )

            if not text:
                return CrawledPage(
                    source=result, content="", success=False, error="Failed to extract text content"
                )

            # Simple truncation strategy
            if len(text) > 15000:
                text = text[:15000] + "\n\n[...Content Truncated...]"

            return CrawledPage(source=result, content=text, success=True)

        except Exception as e:
            logger.warning(f"Error visiting {result.url}: {e}")
            return CrawledPage(source=result, content="", success=False, error=str(e))

    def run(self, query: str) -> List[CrawledPage]:
        """
        Orchestrates the full research process: Search -> Visit.
        """
        logger.info(f"Starting web research for: {query}")

        # 1. Search
        search_results = self.search(query)
        if not search_results:
            return []

        # 2. Visit
        crawled_pages = []
        for search_result in search_results:
            crawled_pages.append(self._visit_page(search_result))

        return crawled_pages


def web_search(query: str, region: str = "wt-wt") -> str:
    """
    Performs a web search and returns a generated summary with sources.
    Uses web_research to get content, then summarizes it.
    """
    try:
        logger.info(f"web_search: Searching for '{query}'...")

        # Get raw content
        with WebResearcher(region=region) as researcher:
            pages = researcher.run(query)

        if not pages:
            return f"Search for '{query}' returned no results or failed."

        # Combine Output
        raw_results = f"## Research Results for: {query}\n\n"
        raw_results += "\n".join([page.to_string() for page in pages])

        if "returned no results" in raw_results:
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
