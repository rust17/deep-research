import asyncio
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from markitdown import MarkItDown
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer

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

                if len(line) > MAX_LINE_LENGTH:
                    line = line[:MAX_LINE_LENGTH] + "..."

                if total_chars + len(line) > MAX_TOTAL_CHARS:
                    remaining = MAX_TOTAL_CHARS - total_chars
                    if remaining > 0:
                        result_parts.append(line[:remaining])
                    return "\n".join(result_parts)

                result_parts.append(line)
                total_chars += len(line)
                lines_count += 1

        if pending_buffer and lines_count < MAX_LINES:
            if total_chars + len(pending_buffer) <= MAX_TOTAL_CHARS:
                result_parts.append(pending_buffer)

        return "\n".join(result_parts)


class FileProcessor:
    """Handles file content extraction."""

    @staticmethod
    async def process(file_path: str, content_type: str, url: str) -> str:
        return await asyncio.to_thread(FileProcessor._extract, file_path, content_type, url)

    @staticmethod
    def _extract(file_path: str, content_type: str, url: str) -> str:
        extension = (
            mimetypes.guess_extension(content_type.split(";")[0]) or Path(url).suffix
        ).lower()

        if "pdf" in content_type.lower() or extension == ".pdf":
            return TextProcessor.normalize_and_limit(FileProcessor._pdf_generator(file_path))

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
