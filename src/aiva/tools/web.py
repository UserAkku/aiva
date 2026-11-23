"""Web skills: news, reading pages, opening sites, YouTube, Wikipedia."""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Literal

import httpx

from ..brain.toolsets import ToolRegistry
from .system import open_target

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/605.1.15 AIVA/0.1"}


async def _ddgs(method: str, query: str, **kwargs: object) -> list[dict]:
    from ddgs import DDGS

    def run() -> list[dict]:
        return list(getattr(DDGS(), method)(query, **kwargs))

    return await asyncio.wait_for(asyncio.to_thread(run), timeout=12)


def register(reg: ToolRegistry) -> None:
    @reg.tool("web")
    async def news_headlines(
        topic: str = "", region: Literal["india", "world"] = "india", max_results: int = 5
    ) -> str:
        """Latest news headlines, optionally about a topic.

        Args:
            topic: e.g. "cricket", "AI", "Delhi weather". Empty for top news.
            region: India or world news.
            max_results: 1 to 8.
        """
        query = topic or ("India top news" if region == "india" else "world top news")
        try:
            items = await _ddgs(
                "news",
                query,
                region="in-en" if region == "india" else "wt-wt",
                max_results=min(max_results, 8),
            )
        except Exception as exc:
            return f"News search failed: {exc}"
        if not items:
            return "No news found."
        return "\n".join(
            f"- {i.get('title')} ({i.get('source')}, {str(i.get('date', ''))[:10]})" for i in items
        )

    @reg.tool("web")
    async def read_webpage(url: str) -> str:
        """Fetch a web page and return its main text (for summarising articles).

        Args:
            url: Full http(s) URL.
        """
        import trafilatura

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            async with httpx.AsyncClient(headers=_UA, follow_redirects=True, timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception as exc:
            return f"Could not open the page: {exc}"
        text = await asyncio.to_thread(trafilatura.extract, resp.text, include_comments=False)
        if not text:
            return "The page has no readable text."
        return text[:3000] + (" …" if len(text) > 3000 else "")

    @reg.tool("web")
    async def open_website(target: str) -> str:
        """Open a website in the Mac's browser. Give a URL/domain, or words to Google search.

        Args:
            target: e.g. "github.com", "https://youtube.com", or "best pizza near me".
        """
        looks_like_url = re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", target.strip()) is not None
        if looks_like_url:
            url = target if target.startswith("http") else "https://" + target.strip()
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(target)
        ok, err = await open_target(url)
        return f"Opened {url}" if ok else f"Could not open browser: {err}"

    @reg.tool("web")
    async def play_youtube(query: str) -> str:
        """Find a video or song on YouTube and play it in the browser.

        Args:
            query: Song/video to play, e.g. "Kesariya song", "lofi beats".
        """
        url = None
        try:
            videos = await _ddgs("videos", query + " youtube", max_results=6)
            for v in videos:
                link = v.get("content") or v.get("url") or ""
                if "youtube.com/watch" in link or "youtu.be/" in link:
                    url, title = link, v.get("title", query)
                    break
        except Exception:
            videos = []
        if url is None:
            url, title = (
                "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query),
                query,
            )
        ok, err = await open_target(url)
        return f"Playing '{title}' on YouTube." if ok else f"Could not open YouTube: {err}"

    @reg.tool("web")
    async def wikipedia_summary(topic: str, language: Literal["en", "hi"] = "en") -> str:
        """Short encyclopedia summary of a person, place or thing from Wikipedia.

        Args:
            topic: What to look up.
            language: Wikipedia language edition.
        """
        base = f"https://{language}.wikipedia.org"
        try:
            async with httpx.AsyncClient(headers=_UA, timeout=10) as client:
                search = await client.get(
                    f"{base}/w/api.php",
                    params={"action": "opensearch", "search": topic, "limit": 1, "format": "json"},
                )
                titles = search.json()[1]
                if not titles:
                    return "No Wikipedia article found."
                page = await client.get(f"{base}/api/rest_v1/page/summary/{urllib.parse.quote(titles[0])}")
                data = page.json()
        except Exception as exc:
            return f"Wikipedia lookup failed: {exc}"
        return f"{data.get('title')}: {data.get('extract', '')[:1200]}"
