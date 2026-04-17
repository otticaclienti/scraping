from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings


def _redis_settings_from_url(url: str) -> RedisSettings:
    # redis://host:port/db
    from urllib.parse import urlparse

    p = urlparse(url)
    return RedisSettings(
        host=p.hostname or "redis",
        port=p.port or 6379,
        database=int(p.path.lstrip("/") or "0"),
    )


_pool: ArqRedis | None = None


async def get_arq() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings_from_url(settings.redis_url))
    return _pool


async def close_arq() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
