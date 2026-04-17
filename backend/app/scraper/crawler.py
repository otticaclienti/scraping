from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.scraper.extractor import (
    COMMON_SUBPATHS,
    JUNK_EXTENSIONS,
    extract_emails,
)
from app.scraper.fetcher import HttpFetcher, PlaywrightFetcher
from app.scraper.validator import has_mx_record, is_syntactically_valid

SITEMAP_URL_RE = re.compile(r"<loc>(.*?)</loc>", re.IGNORECASE)

CONTACT_HINTS = (
    "contatt",
    "contact",
    "about",
    "chi-siamo",
    "team",
    "staff",
    "people",
    "imprint",
    "impressum",
    "legal",
    "privacy",
    "info",
)


@dataclass
class CrawlConfig:
    timeout_seconds: int = 15
    max_pages_per_site: int = 8
    max_attempts: int = 2
    render_js_fallback: bool = True
    verify_mx: bool = False
    follow_sitemap: bool = True
    user_agent: str = "Mozilla/5.0"


@dataclass
class SiteResult:
    url: str
    emails: dict[str, str] = field(default_factory=dict)  # email -> source_page
    attempts: int = 0
    error: str | None = None
    status: str = "done"  # done | failed


def _normalize_root(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"


def _same_host(a: str, b: str) -> bool:
    try:
        pa = urlparse(a).netloc.lower()
        pb = urlparse(b).netloc.lower()
    except Exception:
        return False
    return pa == pb or pa.removeprefix("www.") == pb.removeprefix("www.")


def _discover_links(html: str, base_url: str) -> list[str]:
    out: list[str] = []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if href.lower().endswith(JUNK_EXTENSIONS):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if not _same_host(absolute, base_url):
            continue
        out.append(absolute)
    return out


def _prioritize_links(links: list[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        low = link.lower()
        score = 0
        for hint in CONTACT_HINTS:
            if hint in low:
                score += 10
                break
        scored.append((score, link))
    scored.sort(key=lambda x: -x[0])
    return [link for _, link in scored]


async def _fetch_sitemap_urls(fetcher: HttpFetcher, root: str) -> list[str]:
    urls: list[str] = []
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        res = await fetcher.get(urljoin(root, path))
        if res and res.html:
            for loc in SITEMAP_URL_RE.findall(res.html):
                loc = loc.strip()
                if loc.startswith(("http://", "https://")):
                    urls.append(loc)
    return urls


async def crawl_site(
    url: str,
    config: CrawlConfig,
    http: HttpFetcher,
    playwright: PlaywrightFetcher | None,
) -> SiteResult:
    """Crawl a single website and collect emails."""
    root = _normalize_root(url)
    result = SiteResult(url=root)
    visited: set[str] = set()
    queue: list[str] = [root]

    # Prime the queue with common contact paths and optional sitemap entries
    for sub in COMMON_SUBPATHS:
        queue.append(urljoin(root + "/", sub.lstrip("/")))

    if config.follow_sitemap:
        try:
            sm_urls = await _fetch_sitemap_urls(http, root)
        except Exception:
            sm_urls = []
        for sm_url in sm_urls:
            if _same_host(sm_url, root):
                queue.append(sm_url)

    pages_fetched = 0
    homepage_had_content = False
    all_emails: dict[str, str] = {}

    while queue and pages_fetched < config.max_pages_per_site:
        target = queue.pop(0)
        if target in visited:
            continue
        visited.add(target)

        page_result = None
        for attempt in range(config.max_attempts):
            result.attempts += 1
            page_result = await http.get(target)
            if page_result and page_result.status < 500 and page_result.html:
                break
        if not page_result or not page_result.html:
            continue
        pages_fetched += 1
        if target == root:
            homepage_had_content = True

        emails = extract_emails(page_result.html, page_result.url)
        for e in emails:
            all_emails.setdefault(e, page_result.url)

        # Enqueue same-host contact-like links discovered on the homepage
        if target == root:
            discovered = _discover_links(page_result.html, page_result.url)
            for link in _prioritize_links(discovered):
                if link not in visited and len(queue) < 200:
                    queue.append(link)

    # JS fallback when we found nothing and got very little HTML
    if not all_emails and config.render_js_fallback and playwright is not None:
        try:
            rendered = await playwright.get(root)
            if rendered and rendered.html:
                for e in extract_emails(rendered.html, rendered.url):
                    all_emails.setdefault(e, rendered.url)
        except Exception as exc:
            result.error = f"playwright: {exc}"[:500]

    # Validate
    validated: dict[str, str] = {}
    for email, source in all_emails.items():
        if not is_syntactically_valid(email):
            continue
        if config.verify_mx:
            domain = email.split("@", 1)[1]
            ok = await has_mx_record(domain)
            if not ok:
                continue
        validated[email] = source

    result.emails = validated

    if pages_fetched == 0 and not homepage_had_content:
        result.status = "failed"
        if not result.error:
            result.error = "No reachable pages"
    else:
        result.status = "done"

    return result
