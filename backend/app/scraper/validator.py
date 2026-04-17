from __future__ import annotations

import asyncio
from email_validator import EmailNotValidError, validate_email

try:
    import dns.asyncresolver  # type: ignore

    _HAS_DNS = True
except ImportError:
    _HAS_DNS = False


_mx_cache: dict[str, bool] = {}
_mx_lock = asyncio.Lock()


def is_syntactically_valid(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


async def has_mx_record(domain: str, timeout: float = 4.0) -> bool:
    if not _HAS_DNS:
        return True
    async with _mx_lock:
        if domain in _mx_cache:
            return _mx_cache[domain]
    try:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answer = await resolver.resolve(domain, "MX")
        ok = bool(list(answer))
    except Exception:
        ok = False
    async with _mx_lock:
        _mx_cache[domain] = ok
    return ok
