import logging
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import html2text
from ddgs import DDGS

from .web_fetch import web_fetch
from .search import google_web_search
from .todo import write_todos
from .ls import list_directory
from .read_file import read_file
from .write_file import write_file
from .glob import glob
from .grep import search_file_content
from .edit import replace

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 屏蔽第三方库的冗余日志
logging.getLogger("primp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("ddgs").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def web_research(query: str, max_links: int = 5) -> str:
    """
    综合研究工具：执行搜索并自动访问前几个链接。
    1. 搜索关键词。
    2. 提取前 max_links 个 URL。
    3. 并发访问这些 URL 获取全文。
    4. 返回整合后的内容。
    """
    logger.info(f"Starting web research for: {query}")

    # 1. Search
    try:
        raw_results = []
        with DDGS() as ddgs:
            # 获取比 max_links 稍多一点的结果，以防部分链接无效
            ddgs_gen = ddgs.text(query, region="cn-zh", max_results=max_links + 2)
            if ddgs_gen:
                raw_results = list(ddgs_gen)

        if not raw_results:
            return f"Search for '{query}' returned no results."

        # 提取 URL 和 标题
        targets = []
        for res in raw_results[:max_links]:
            link = res.get('href')
            title = res.get('title', 'No Title')
            if link:
                targets.append({"url": link, "title": title})

        logger.info(f"Found {len(targets)} links to visit.")

    except Exception as e:
        logger.error(f"Search phase failed: {e}")
        return f"Search failed: {str(e)}"

    # 2. Batch Visit
    if not targets:
        return "Search returned results but no valid URLs found."

    visited_content = []
    with ThreadPoolExecutor(max_workers=max_links) as executor:
        future_to_url = {
            executor.submit(_visit_page_internal, t["url"]): t["title"]
            for t in targets
        }

        for future in as_completed(future_to_url):
            title = future_to_url[future]
            try:
                content = future.result()
                visited_content.append(f"=== Source: {title} ===\n{content}\n")
            except Exception as exc:
                visited_content.append(f"=== Source: {title} ===\nFailed to load: {exc}\n")

    # 3. Combine Output
    final_output = f"## Research Results for: {query}\n\n"
    final_output += "\n".join(visited_content)

    return final_output

def _visit_page_internal(url: str, timeout: int = 15) -> str:
    """
    内部使用的单页访问函数
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

        # 清洗
        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "svg"]):
            element.decompose()

        # 转 Markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        h.protect_links = True

        text = h.handle(str(soup))

        # 增加 Source URL 标记
        text = f"URL: {url}\n\n{text}"

        # 截断
        if len(text) > 15000:
            text = text[:15000] + "\n\n[...Content Truncated...]"

        return text

    except Exception as e:
        # logger.warning(f"Failed to visit {url}: {e}") # Reduce noise
        raise e