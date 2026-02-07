import asyncio
import contextlib
from dataclasses import dataclass

import trafilatura
from playwright.async_api import BrowserContext, async_playwright

from ..llm_client import LLMClient
from ..logs import console


@dataclass
class SearchResult:
    """Represents a single search result item."""

    title: str
    url: str
    snippet: str | None = None


@dataclass
class CrawledPage:
    """Represents the content extracted from a visited page."""

    source: SearchResult
    content: str
    success: bool
    error: str | None = None

    def to_string(self) -> str:
        """Formats the page content for display/LLM consumption."""
        header = f"=== Source: {self.source.title} ==="
        if not self.success:
            return f"{header}\nURL: {self.source.url}\nFailed to load: {self.error}\n"

        return f"{header}\nURL: {self.source.url}\n\n{self.content}\n"


class WebResearcher:
    """
    Encapsulates web research logic using Playwright (Async) and Trafilatura.
    """

    def __init__(self, region: str = "wt-wt", timeout: int = 30000, headless: bool = True):
        self.region = region
        self.timeout = timeout  # ms
        self.headless = headless
        self.semaphore = asyncio.Semaphore(5)

    async def _search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Performs the search using DDGS in an executor."""
        from ddgs import DDGS

        def _ssearch():
            with DDGS() as ddgs:
                return list(
                    ddgs.text(query, region=self.region, safesearch="on", max_results=max_results)
                )

        results = []
        try:
            loop = asyncio.get_running_loop()
            ddgs_results = await loop.run_in_executor(None, _ssearch)

            if ddgs_results:
                for res in ddgs_results:
                    link = res.get("href")
                    title = res.get("title", "No Title")
                    body = res.get("body", "")
                    if link:
                        results.append(SearchResult(title=title, url=link, snippet=body))

            console.info(f"Found {len(results)} valid links for query: {query}")
            return results
        except Exception as e:
            console.error(f"Search phase failed: {e}")
            return []

    async def _visit_page(self, context: BrowserContext, result: SearchResult) -> CrawledPage:
        """Internal method to visit a page with Playwright and extract content."""
        async with self.semaphore:
            page = await context.new_page()
            try:
                # Intercept and block unnecessary resources
                await page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ["image", "media", "font"]
                    else route.continue_(),
                )

                # Retry logic for page loading: Max 3 attempts
                for attempt in range(3):
                    try:
                        # 'domcontentloaded' is faster and sufficient for text extraction
                        await page.goto(result.url, wait_until="domcontentloaded", timeout=self.timeout)
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise
                        console.warning(f"Retry {attempt + 1} for {result.url} due to: {e}")
                        await asyncio.sleep(2)

                # Extra safety: if page is still navigating, content() might fail
                content = ""
                for _ in range(3):
                    try:
                        content = await page.content()
                        break
                    except Exception as e:
                        if "navigating" in str(e).lower():
                            await asyncio.sleep(1)
                            continue
                        raise

                # Extract text using trafilatura in a thread (CPU bound)
                loop = asyncio.get_running_loop()
                text = await loop.run_in_executor(
                    None,
                    lambda: trafilatura.extract(
                        content,
                        include_links=True,
                        include_comments=False,
                        include_tables=True,
                        no_fallback=False,
                    ),
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
                console.warning(f"Error visiting {result.url}: {e}")
                return CrawledPage(source=result, content="", success=False, error=str(e))
            finally:
                await page.close()

    async def run(self, query: str) -> list[CrawledPage]:
        """
        Orchestrates the full research process: Search -> Visit (Parallel).
        """
        # 1. Search
        search_results = await self._search(query)
        if not search_results:
            return []

        # 2. Visit
        crawled_pages = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                )

                # Execute visits in parallel
                tasks = [self._visit_page(context, res) for res in search_results]
                crawled_pages = await asyncio.gather(*tasks)

                await context.close()
                await browser.close()

        except Exception as e:
            console.error(f"Browser execution failed: {e}")

        return crawled_pages


async def _aresearch(query: str, region: str) -> list[CrawledPage]:
    researcher = WebResearcher(region=region)
    return await researcher.run(query)


def web_search(query: str, region: str = "wt-wt") -> str:
    """
    Performs a web search and returns a generated summary with sources.
    Uses async WebResearcher internally.
    """
    try:
        console.info(f"web_search: Searching for '{query}'...")

        # Run Async Pipeline via asyncio.run
        pages = asyncio.run(_aresearch(query, region))

        if not pages:
            return f"Search for '{query}' returned no results or failed."

        # Combine Output
        raw_results = f"## Research Results for: {query}\n\n"
        raw_results += "\n".join([page.to_string() for page in pages])

        if "returned no results" in raw_results:
            return raw_results

        # Summarize with LLM (Sync)
        llm = LLMClient()
        prompt = f"""
You are given a piece of content and the requirement of information to extract. Your task is to extract the information specifically requested. Be precise and focus exclusively on the requested information.

INFORMATION TO EXTRACT:
{query}

INSTRUCTIONS:
1. Extract the information relevant to the focus above.
2. If the exact information is not found, extract the most closely related details.
3. Be specific and include exact details when available.
4. Clearly organize the extracted information for easy understanding.
5. Do not include general summaries or unrelated content.

CONTENT TO ANALYZE:
{raw_results}

EXTRACTED INFORMATION:
"""
        console.info("web_search: Generating summary...")
        response = llm.query(prompt, model_type="small")
        return response

    except Exception as e:
        console.error(f"web_search failed: {e}")
        return f"Error performing web search: {str(e)}"
