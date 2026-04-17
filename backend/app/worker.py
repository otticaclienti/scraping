from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import tldextract
from arq.connections import RedisSettings
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import BlacklistDomain, Email, Job, Site
from app.queue import _redis_settings_from_url
from app.scraper.crawler import CrawlConfig, crawl_site
from app.scraper.fetcher import HttpFetcher, PlaywrightFetcher

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)


async def _load_blacklist() -> set[str]:
    async with SessionLocal() as s:
        res = await s.execute(select(BlacklistDomain.domain))
        return {d for (d,) in res.all()}


def _registered_domain(url: str) -> str:
    ext = tldextract.extract(url)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return url.lower()


async def _process_site(
    ctx: dict,
    site_id: int,
    config: CrawlConfig,
    blacklist: set[str],
) -> None:
    async with SessionLocal() as s:
        site = await s.get(Site, site_id)
        if not site or site.status in ("done", "skipped"):
            return

        job = await s.get(Job, site.job_id)
        if not job or job.status in ("paused", "stopped"):
            return

        if _registered_domain(site.url) in blacklist:
            site.status = "skipped"
            site.error = "blacklisted"
            site.finished_at = datetime.now(timezone.utc)
            await s.commit()
            return

        site.status = "running"
        site.started_at = datetime.now(timezone.utc)
        await s.commit()

    http: HttpFetcher = ctx["http"]
    playwright: PlaywrightFetcher | None = ctx.get("playwright")

    try:
        result = await crawl_site(site.url, config, http, playwright)
    except Exception as exc:
        logger.exception("crawl failed for %s", site.url)
        async with SessionLocal() as s:
            site_obj = await s.get(Site, site_id)
            if site_obj:
                site_obj.status = "failed"
                site_obj.error = f"crawler: {exc}"[:500]
                site_obj.finished_at = datetime.now(timezone.utc)
                await s.commit()
        return

    async with SessionLocal() as s:
        site_obj = await s.get(Site, site_id)
        if not site_obj:
            return
        site_obj.attempts = result.attempts
        site_obj.status = result.status
        site_obj.error = result.error
        site_obj.emails_found = len(result.emails)
        site_obj.finished_at = datetime.now(timezone.utc)

        for email, source in result.emails.items():
            stmt = pg_insert(Email).values(
                site_id=site_id,
                job_id=site_obj.job_id,
                email=email,
                source_page=source,
            ).on_conflict_do_nothing(index_elements=["site_id", "email"])
            await s.execute(stmt)

        await s.commit()


async def scrape_job(ctx: dict, job_id: int) -> None:
    """Fan out work for every pending site in the given job."""
    concurrency = settings.worker_concurrency
    blacklist = await _load_blacklist()

    async with SessionLocal() as s:
        job = await s.get(Job, job_id)
        if not job:
            return
        cfg = CrawlConfig(
            timeout_seconds=job.config.get("timeout_seconds", 15),
            max_pages_per_site=job.config.get("max_pages_per_site", 8),
            max_attempts=job.config.get("max_attempts", 2),
            render_js_fallback=job.config.get("render_js_fallback", True),
            verify_mx=job.config.get("verify_mx", False),
            follow_sitemap=job.config.get("follow_sitemap", True),
            user_agent=job.config.get("user_agent") or settings.default_user_agent,
        )

    sem = asyncio.Semaphore(concurrency)

    async def run_one(site_id: int) -> None:
        async with sem:
            # re-check job state so pause/stop respond quickly
            async with SessionLocal() as s:
                j = await s.get(Job, job_id)
                if not j or j.status in ("paused", "stopped"):
                    return
            await _process_site(ctx, site_id, cfg, blacklist)

    while True:
        async with SessionLocal() as s:
            j = await s.get(Job, job_id)
            if not j or j.status in ("paused", "stopped"):
                return
            batch = (
                await s.execute(
                    select(Site.id)
                    .where(Site.job_id == job_id, Site.status == "pending")
                    .order_by(Site.id)
                    .limit(concurrency * 4)
                )
            ).scalars().all()

        if not batch:
            break

        await asyncio.gather(*(run_one(sid) for sid in batch))

    # Finalize job status
    async with SessionLocal() as s:
        counts = dict(
            (status, n)
            for status, n in (
                await s.execute(
                    select(Site.status, func.count())
                    .where(Site.job_id == job_id)
                    .group_by(Site.status)
                )
            ).all()
        )
        j = await s.get(Job, job_id)
        if not j:
            return
        if counts.get("pending", 0) == 0 and counts.get("running", 0) == 0:
            j.status = "done"
        await s.commit()


async def startup(ctx: dict) -> None:
    # Make sure tables exist before we touch them (handles worker
    # starting before or alongside the backend on first boot).
    await init_db()

    http = HttpFetcher(settings.default_user_agent, timeout=settings.default_timeout_seconds)
    await http.start()
    ctx["http"] = http
    ctx["playwright"] = PlaywrightFetcher(
        settings.default_user_agent, timeout=settings.default_timeout_seconds
    )
    # Reset any sites stuck in "running" state (e.g. after a crash)
    async with SessionLocal() as s:
        await s.execute(
            update(Site).where(Site.status == "running").values(status="pending")
        )
        await s.commit()


async def shutdown(ctx: dict) -> None:
    if http := ctx.get("http"):
        await http.close()
    if pw := ctx.get("playwright"):
        await pw.close()


class WorkerSettings:
    functions = [scrape_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings: RedisSettings = _redis_settings_from_url(settings.redis_url)
    max_jobs = 4
    job_timeout = 60 * 60 * 6  # 6 hours per fan-out
    keep_result = 0
