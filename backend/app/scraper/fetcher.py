from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx


@dataclass
class FetchResult:
    url: str
    status: int
    html: str
    rendered: bool = False


class HttpFetcher:
    """Async HTTP fetcher with timeout, redirects, and content-type guarding."""

    def __init__(self, user_agent: str, timeout: float) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        }
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
                verify=False,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str) -> FetchResult | None:
        assert self._client is not None
        try:
            resp = await self._client.get(url)
        except (httpx.HTTPError, asyncio.TimeoutError):
            return None
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type:
            return FetchResult(url=str(resp.url), status=resp.status_code, html="")
        try:
            text = resp.text
        except Exception:
            text = ""
        return FetchResult(url=str(resp.url), status=resp.status_code, html=text)


@asynccontextmanager
async def http_fetcher(user_agent: str, timeout: float):
    fetcher = HttpFetcher(user_agent, timeout)
    await fetcher.start()
    try:
        yield fetcher
    finally:
        await fetcher.close()


class PlaywrightFetcher:
    """Fallback renderer for JS-heavy pages. Lazy-imported and lazy-started."""

    def __init__(self, user_agent: str, timeout: float) -> None:
        self.user_agent = user_agent
        self.timeout_ms = int(timeout * 1000)
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._browser is not None:
                return
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )

    async def close(self) -> None:
        async with self._lock:
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._pw is not None:
                await self._pw.stop()
                self._pw = None

    async def get(self, url: str) -> FetchResult | None:
        await self.start()
        assert self._browser is not None
        context = await self._browser.new_context(user_agent=self.user_agent)
        page = await context.new_page()
        try:
            resp = await page.goto(
                url, timeout=self.timeout_ms, wait_until="networkidle"
            )
            status = resp.status if resp else 0
            html = await page.content()
            final_url = page.url
            return FetchResult(url=final_url, status=status, html=html, rendered=True)
        except Exception:
            return None
        finally:
            await context.close()
