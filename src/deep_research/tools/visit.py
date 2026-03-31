import asyncio
import mimetypes
import shutil
import tempfile
from pathlib import Path

import trafilatura
from playwright.async_api import BrowserContext, Download, Page, Response, async_playwright

from ..llm_client import LLMClient
from ..log import log
from ..prompt import VISIT_SUMMARIZE_PROMPT
from ._base import (
    GLOBAL_RESULT_LIMIT,
    SEARCH_TIMEOUT,
    USER_AGENT,
    CrawledPage,
    FileProcessor,
    SearchResult,
    TextProcessor,
)


class BrowserCrawler:
    """Handles page visiting and crawling logic using Playwright."""

    def __init__(self, timeout: int = SEARCH_TIMEOUT):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(5)

    async def crawl(self, results: list[SearchResult], headless: bool = True) -> list[CrawledPage]:
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
            log.error(f"Browser execution failed: {e}")
            return []

    async def _visit(self, context: BrowserContext, result: SearchResult) -> CrawledPage:
        async with self.semaphore:
            page = await context.new_page()
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
                    if "Download is starting" not in str(e) and "net::ERR_ABORTED" not in str(e):
                        log.warning(f"Navigation error for {result.url}: {e}")

                download = await self._check_download(download_task, response)

                if download:
                    content = await self._handle_download(download, result.url)
                elif response:
                    content = await self._handle_response(page, response, result.url)
                else:
                    error_msg = "No response and no download detected"

            except Exception as e:
                log.warning(f"Error visiting {result.url}: {e}")
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
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "media", "font"]
            else route.continue_(),
        )

    async def _check_download(
        self, download_task: asyncio.Task, response: Response | None
    ) -> Download | None:
        try:
            if download_task.done():
                return await download_task
            elif not response:
                return await asyncio.wait_for(download_task, timeout=1.0)
        except Exception:
            pass
        return None

    async def _handle_download(self, download: Download, url: str) -> str:
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
        if "application/pdf" in content_type or "application/octet-stream" in content_type:
            return True
        if any(ext in url.lower() for ext in [".pdf", ".docx", ".pptx", ".xlsx"]):
            return True
        return False


def _format_results(pages: list[CrawledPage]) -> str:
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


def visit(url: str, goal: str = "Extract key information") -> dict:
    """
    Visit a specific URL and return its summarized content.
    """
    try:
        log.info(f"visit: Visiting {url}...")
        search_result = SearchResult(title="Target Page", url=url)

        crawler = BrowserCrawler()
        pages = asyncio.run(crawler.crawl([search_result]))

        if not pages or not pages[0].success:
            error = pages[0].error if pages else "Unknown error"
            return {"type": "text", "text": f"Failed to visit {url}: {error}"}

        raw_results = _format_results(pages)

        llm = LLMClient()

        prompt: list[dict[str, str]] = []
        prompt.append({"role": "system", "content": VISIT_SUMMARIZE_PROMPT.format(goal=goal)})
        prompt.append(
            {
                "role": "user",
                "content": f"""
CONTENT TO ANALYZE:
{raw_results}
EXTRACTED INFORMATION:
""",
            }
        )
        log.info(f"visit: Generating summary for {url}...")
        response = llm.query(prompt)
        return {"type": "text", "text": response}

    except Exception as e:
        log.error(f"visit failed: {e}")
        return {"type": "text", "text": f"Error visiting URL: {str(e)}"}
