"""Email extraction and de-obfuscation.

Handles common tricks used to hide emails on web pages:
- [at] / (at) / {at} / " at " replacements
- [dot] / (dot) / " dot " replacements
- HTML entity encoding (&#64; etc.)
- Cloudflare email protection (data-cfemail)
- mailto: links including those with subject/body params
"""
from __future__ import annotations

import html
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24})"
    r"(?![A-Za-z0-9._%+\-])"
)

AT_PATTERNS = [
    (re.compile(r"\s*\[\s*at\s*\]\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s*\(\s*at\s*\)\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s*\{\s*at\s*\}\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s+at\s+", re.IGNORECASE), "@"),
    (re.compile(r"\s*&#64;\s*"), "@"),
    (re.compile(r"\s*&#0*64;\s*"), "@"),
]

DOT_PATTERNS = [
    (re.compile(r"\s*\[\s*dot\s*\]\s*", re.IGNORECASE), "."),
    (re.compile(r"\s*\(\s*dot\s*\)\s*", re.IGNORECASE), "."),
    (re.compile(r"\s*\{\s*dot\s*\}\s*", re.IGNORECASE), "."),
    (re.compile(r"\s+dot\s+", re.IGNORECASE), "."),
    (re.compile(r"\s*&#46;\s*"), "."),
]

# Only trust obfuscation when it appears near an email-like fragment (letters + tld)
OBFUSCATED_CANDIDATE_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+\s*(?:\[at\]|\(at\)|\{at\}|\sat\s|&#64;)\s*"
    r"[A-Za-z0-9.\-]+\s*(?:\[dot\]|\(dot\)|\{dot\}|\sdot\s|&#46;|\.)\s*[A-Za-z]{2,24}",
    re.IGNORECASE,
)

COMMON_SUBPATHS = [
    "/contatti",
    "/contact",
    "/contact-us",
    "/contacts",
    "/about",
    "/about-us",
    "/chi-siamo",
    "/team",
    "/staff",
    "/people",
    "/imprint",
    "/impressum",
    "/legal",
    "/privacy",
    "/privacy-policy",
    "/informazioni",
    "/info",
    "/help",
    "/support",
]

JUNK_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
    ".ico", ".css", ".js",
)


def _decode_cf_email(encoded: str) -> str | None:
    """Decode Cloudflare's obfuscated emails (data-cfemail attribute)."""
    try:
        r = int(encoded[:2], 16)
        return "".join(
            chr(int(encoded[i : i + 2], 16) ^ r)
            for i in range(2, len(encoded), 2)
        )
    except (ValueError, IndexError):
        return None


def _deobfuscate_text(text: str) -> str:
    # Only deobfuscate chunks that actually look email-ish,
    # to avoid corrupting sentences like "meet at the dot"
    def replace(match: re.Match[str]) -> str:
        fragment = match.group(0)
        for pat, sub in AT_PATTERNS:
            fragment = pat.sub(sub, fragment)
        for pat, sub in DOT_PATTERNS:
            fragment = pat.sub(sub, fragment)
        return fragment

    return OBFUSCATED_CANDIDATE_RE.sub(replace, text)


def extract_emails(html_text: str, base_url: str = "") -> set[str]:
    """Return all distinct emails discovered in HTML."""
    emails: set[str] = set()
    if not html_text:
        return emails

    # Unescape HTML entities first
    decoded = html.unescape(html_text)

    try:
        soup = BeautifulSoup(html_text, "lxml")
    except Exception:
        soup = BeautifulSoup(html_text, "html.parser")

    # mailto: links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?", 1)[0]
            addr = unquote(addr).strip()
            if addr:
                emails.add(addr.lower())

    # Cloudflare email protection
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        decoded_cf = _decode_cf_email(tag["data-cfemail"])
        if decoded_cf:
            emails.add(decoded_cf.lower())

    # Visible text, deobfuscated
    text_fragments: list[str] = []
    for el in soup(["script", "style", "noscript"]):
        el.decompose()
    body_text = soup.get_text(separator=" ", strip=True)
    text_fragments.append(body_text)
    # Also scan full raw HTML (emails can live in attributes or JSON blobs)
    text_fragments.append(decoded)

    for fragment in text_fragments:
        fragment = _deobfuscate_text(fragment)
        for match in EMAIL_RE.findall(fragment):
            emails.add(match.lower())

    # Filter out clearly junk entries
    return {e for e in emails if _is_plausible(e)}


def _is_plausible(email: str) -> bool:
    if len(email) > 254 or len(email) < 6:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if email.endswith(JUNK_EXTENSIONS):
        # e.g. "img@2x.png" false positives
        return False
    # Sentry/wix/etc placeholder sentinels
    if any(s in email for s in ("example.com", "yourdomain", "domain.com", "email.com")):
        return False
    # Filenames that happen to include @
    if re.search(r"@\d+x\.(png|jpg|jpeg|gif|webp|svg)$", email):
        return False
    return True
