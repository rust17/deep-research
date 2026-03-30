import asyncio

from ..log import log
from ._base import SearchResult


class DDG:
    """Handles search queries via DDGS."""

    @staticmethod
    async def search(
        query: str, region: str = "wt-wt", max_results: int = 10
    ) -> list[SearchResult]:
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
            log.info(f"Found {len(parsed_results)} valid links for query: {query}")
            return parsed_results
        except Exception as e:
            log.error(f"Search phase failed: {e}")
            return []


def search(query: str, region: str = "wt-wt") -> dict:
    """
    Search the internet for information. Returns a list of search results with titles, URLs, and snippets.
    """
    try:
        log.info(f"search: Searching for '{query}'...")
        results = asyncio.run(DDG.search(query, region=region))

        if not results:
            return {"type": "text", "text": f"Search for '{query}' returned no results."}

        formatted_results = []
        for i, res in enumerate(results):
            formatted_results.append(f"[{i}] {res.title}\nURL: {res.url}\nSnippet: {res.snippet}\n")

        content = f"Search results for '{query}':\n\n" + "\n".join(formatted_results)
        return {"type": "text", "text": content}

    except Exception as e:
        log.error(f"search failed: {e}")
        return {"type": "text", "text": f"Error performing search: {str(e)}"}
