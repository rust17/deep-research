import asyncio
import mimetypes
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import trafilatura
from markitdown import MarkItDown
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer
from playwright.async_api import BrowserContext, Download, Page, Response, async_playwright

from ..llm_client import LLMClient
from ..logs import console

# --- Configuration ---
MAX_LINE_LENGTH = 2000
MAX_LINES = 1000
MAX_TOTAL_CHARS = 3000
MIN_JOIN_LENGTH = 15
GLOBAL_RESULT_LIMIT = 30000
SEARCH_TIMEOUT = 30000  # ms
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


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


class TextProcessor:
    """Handles text normalization and limiting."""

    @staticmethod
    def normalize_and_limit(text_iterator: Iterator[str]) -> str:
        """
        Applies limits to the text extraction:
        - Max 2000 chars per line (append '...' if exceeded)
        - Max 1000 lines (non-empty)
        - Max 3000 total chars (non-empty)
        - Removes empty lines
        - Joins lines with <= 15 chars with the next line
        """
        total_chars = 0
        lines_count = 0
        result_parts = []
        pending_buffer = ""

        for chunk in text_iterator:
            if not chunk:
                continue
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue

                if pending_buffer:
                    line = f"{pending_buffer} {line}"
                    pending_buffer = ""

                if len(line) <= MIN_JOIN_LENGTH:
                    pending_buffer = line
                    continue

                if lines_count >= MAX_LINES:
                    return "\n".join(result_parts)

                # Truncate line
                if len(line) > MAX_LINE_LENGTH:
                    line = line[:MAX_LINE_LENGTH] + "..."

                # Check total chars
                if total_chars + len(line) > MAX_TOTAL_CHARS:
                    remaining = MAX_TOTAL_CHARS - total_chars
                    if remaining > 0:
                        result_parts.append(line[:remaining])
                    return "\n".join(result_parts)

                result_parts.append(line)
                total_chars += len(line)
                lines_count += 1

        # Handle any remaining content in buffer
        if pending_buffer and lines_count < MAX_LINES:
            if total_chars + len(pending_buffer) <= MAX_TOTAL_CHARS:
                result_parts.append(pending_buffer)

        return "\n".join(result_parts)


class FileProcessor:
    """Handles file content extraction."""

    @staticmethod
    async def process(file_path: str, content_type: str, url: str) -> str:
        """Process a file (PDF, DOCX, etc.) using stream/iterator logic where possible."""
        return await asyncio.to_thread(FileProcessor._extract, file_path, content_type, url)

    @staticmethod
    def _extract(file_path: str, content_type: str, url: str) -> str:
        extension = (
            mimetypes.guess_extension(content_type.split(";")[0]) or Path(url).suffix
        ).lower()

        if "pdf" in content_type.lower() or extension == ".pdf":
            return TextProcessor.normalize_and_limit(FileProcessor._pdf_generator(file_path))

        # Fallback to MarkItDown for other complex formats
        try:
            md = MarkItDown()
            result = md.convert(file_path)
            if result and result.text_content:
                return TextProcessor.normalize_and_limit([result.text_content])
        except Exception as e:
            console.warning(f"MarkItDown extraction failed: {e}")

        return ""

    @staticmethod
    def _pdf_generator(file_path: str) -> Iterator[str]:
        try:
            for page_layout in extract_pages(file_path):
                for element in page_layout:
                    if isinstance(element, LTTextContainer):
                        yield element.get_text()
        except Exception as e:
            console.warning(f"PDF extraction warning: {e}")
            yield ""


class DDG:
    """Handles search queries via DDGS."""

    @staticmethod
    async def search(
        query: str, region: str = "wt-wt", max_results: int = 10
    ) -> List[SearchResult]:
        from ddgs import DDGS

        def _run_ddgs():
            with DDGS() as ddgs:
                return list(
                    ddgs.text(query, region=region, safesearch="on", max_results=max_results)
                )

        try:
            results = await asyncio.to_thread(_run_ddgs)
            parsed_results = []
            if results:
                for res in results:
                    link = res.get("href")
                    if link:
                        parsed_results.append(
                            SearchResult(
                                title=res.get("title", "No Title"),
                                url=link,
                                snippet=res.get("body", ""),
                            )
                        )
            console.info(f"Found {len(parsed_results)} valid links for query: {query}")
            return parsed_results
        except Exception as e:
            console.error(f"Search phase failed: {e}")
            return []


class BrowserCrawler:
    """Handles page visiting and crawling logic using Playwright."""

    def __init__(self, timeout: int = SEARCH_TIMEOUT):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(5)

    async def crawl(self, results: List[SearchResult], headless: bool = True) -> List[CrawledPage]:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    accept_downloads=True,
                )

                tasks = [self._visit(context, res) for res in results]
                pages = await asyncio.gather(*tasks)

                await context.close()
                await browser.close()
                return pages
        except Exception as e:
            console.error(f"Browser execution failed: {e}")
            return []

    async def _visit(self, context: BrowserContext, result: SearchResult) -> CrawledPage:
        async with self.semaphore:
            page = await context.new_page()
            # Setup download listener (wait up to 10s for download start)
            download_task = asyncio.create_task(page.wait_for_event("download", timeout=10000))

            content = ""
            error_msg = None

            try:
                await self._block_resources(page)

                response = None
                try:
                    response = await page.goto(
                        result.url, wait_until="domcontentloaded", timeout=self.timeout
                    )
                except Exception as e:
                    # If navigation failed, check if it was due to a download triggering
                    if "Download is starting" not in str(e) and "net::ERR_ABORTED" not in str(e):
                        console.warning(f"Navigation error for {result.url}: {e}")

                # Check for download
                download = await self._check_download(download_task, response)

                if download:
                    content = await self._handle_download(download, result.url)
                elif response:
                    content = await self._handle_response(page, response, result.url)
                else:
                    error_msg = "No response and no download detected"

            except Exception as e:
                console.warning(f"Error visiting {result.url}: {e}")
                error_msg = str(e)
            finally:
                if not download_task.done():
                    download_task.cancel()
                await page.close()

            if not content and not error_msg:
                error_msg = "No content extracted"

            return CrawledPage(
                source=result,
                content=content,
                success=bool(content),
                error=error_msg,
            )

    async def _block_resources(self, page: Page):
        """Intercept and block unnecessary resources."""
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_(),
        )

    async def _check_download(
        self, download_task: asyncio.Task, response: Optional[Response]
    ) -> Optional[Download]:
        """Determine if a download occurred."""
        try:
            if download_task.done():
                return await download_task
            elif not response:
                # If no response, wait briefly for download
                return await asyncio.wait_for(download_task, timeout=1.0)
        except Exception:
            pass
        return None

    async def _handle_download(self, download: Download, url: str) -> str:
        """Process a downloaded file."""
        temp_path = await download.path()
        suggested_filename = download.suggested_filename
        content_type = mimetypes.guess_type(suggested_filename)[0] or "application/octet-stream"
        ext = Path(suggested_filename).suffix

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            target_path = tf.name

        shutil.copy(temp_path, target_path)

        try:
            return await FileProcessor.process(target_path, content_type, url)
        finally:
            Path(target_path).unlink(missing_ok=True)

    async def _handle_response(self, page: Page, response: Response, url: str) -> str:
        """Process a direct HTTP response (HTML or inline file)."""
        content_type = response.headers.get("content-type", "").lower()

        if self._is_file_content(content_type, url):
            ext = mimetypes.guess_extension(content_type.split(";")[0]) or Path(url).suffix
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
                temp_path = tf.name
                tf.write(await response.body())
            try:
                return await FileProcessor.process(temp_path, content_type, url)
            finally:
                Path(temp_path).unlink(missing_ok=True)

        # HTML Processing
        html = ""
        for _ in range(3):
            try:
                html = await page.content()
                break
            except Exception as e:
                if "navigating" in str(e).lower():
                    await asyncio.sleep(1)
                    continue
                raise

        text = await asyncio.to_thread(
            trafilatura.extract,
            html,
            include_links=True,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        return TextProcessor.normalize_and_limit([text or ""])

    def _is_file_content(self, content_type: str, url: str) -> bool:
        """Check if content type or URL suggests a file download."""
        if "application/pdf" in content_type or "application/octet-stream" in content_type:
            return True
        if any(ext in url.lower() for ext in [".pdf", ".docx", ".pptx", ".xlsx"]):
            return True
        return False


def _format_results(pages: List[CrawledPage]) -> str:
    """Combines crawled pages into a single string with global limits."""
    raw_results = ""
    current_total = 0

    for page in pages:
        page_str = page.to_string()
        if current_total + len(page_str) > GLOBAL_RESULT_LIMIT:
            remaining = GLOBAL_RESULT_LIMIT - current_total
            if remaining > 0:
                raw_results += page_str[:remaining] + "\n[...Total Content Limit Reached...]"
            break
        raw_results += page_str
        current_total += len(page_str)

    return raw_results


def search(query: str, region: str = "wt-wt") -> dict:
    """
    Search the internet for information. Returns a list of search results with titles, URLs, and snippets.
    """
    try:
        console.info(f"search: Searching for '{query}'...")
        results = asyncio.run(DDG.search(query, region=region))

        if not results:
            return {"type": "text", "text": f"Search for '{query}' returned no results."}

        formatted_results = []
        for i, res in enumerate(results):
            formatted_results.append(f"[{i}] {res.title}\nURL: {res.url}\nSnippet: {res.snippet}\n")

        content = f"Search results for '{query}':\n\n" + "\n".join(formatted_results)
        return {"type": "text", "text": content}

    except Exception as e:
        console.error(f"search failed: {e}")
        return {"type": "text", "text": f"Error performing search: {str(e)}"}


def visit(url: str, goal: str = "Extract key information") -> dict:
    """
    Visit a specific URL and return its summarized content.
    """
    try:
        console.info(f"visit: Visiting {url}...")
        search_result = SearchResult(title="Target Page", url=url)

        pages = asyncio.run(BrowserCrawler.crawl([search_result]))

        if not pages or not pages[0].success:
            error = pages[0].error if pages else "Unknown error"
            return {"type": "text", "text": f"Failed to visit {url}: {error}"}

        raw_results = _format_results(pages)

        # Summarize with LLM
        llm = LLMClient()
        prompt = f"""
You are given a piece of content and the requirement of information to extract. Your task is to extract the information specifically requested. Be precise and focus exclusively on the requested information.

INFORMATION TO EXTRACT / GOAL:
{goal}

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
        console.info(f"visit: Generating summary for {url}...")
        response = llm.query(prompt, model_type="small")
        return {"type": "text", "text": response}

    except Exception as e:
        console.error(f"visit failed: {e}")
        return {"type": "text", "text": f"Error visiting URL: {str(e)}"}
