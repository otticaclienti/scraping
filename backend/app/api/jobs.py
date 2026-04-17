from __future__ import annotations

import csv
import io
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Email, Job, Site
from app.queue import get_arq
from app.schemas import JobConfig, JobRead, JobStats, SiteRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _parse_urls(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip().strip(",;")
        if not line or line.startswith("#"):
            continue
        out.append(line)
    # dedup preserve order
    seen: set[str] = set()
    unique = []
    for u in out:
        key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(u)
    return unique


@router.post("", response_model=JobRead)
async def create_job(
    name: Annotated[str, Form()],
    config_json: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
    urls_text: Annotated[str, Form()] = "",
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> JobRead:
    if not file and not urls_text.strip():
        raise HTTPException(400, "Provide file or urls_text")

    raw = ""
    if file:
        data = await file.read()
        raw = data.decode("utf-8", errors="ignore")
    if urls_text:
        raw = raw + "\n" + urls_text

    urls = _parse_urls(raw)
    if not urls:
        raise HTTPException(400, "No URLs found")

    config = JobConfig.model_validate_json(config_json) if config_json else JobConfig()

    job = Job(
        name=name,
        status="running",
        config=config.model_dump(),
        total_sites=len(urls),
    )
    session.add(job)
    await session.flush()

    session.add_all([Site(job_id=job.id, url=u) for u in urls])
    await session.commit()
    await session.refresh(job)

    # enqueue each site
    await arq.enqueue_job("scrape_job", job.id, _job_id=f"job-kickoff-{job.id}")

    return JobRead.model_validate(job)


@router.get("", response_model=list[JobRead])
async def list_jobs(session: AsyncSession = Depends(get_session)) -> list[JobRead]:
    result = await session.execute(select(Job).order_by(Job.id.desc()))
    return [JobRead.model_validate(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=JobStats)
async def job_stats(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> JobStats:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    counts_q = await session.execute(
        select(Site.status, func.count()).where(Site.job_id == job_id).group_by(Site.status)
    )
    counts = {status: n for status, n in counts_q.all()}

    emails_q = await session.execute(
        select(func.count()).select_from(Email).where(Email.job_id == job_id)
    )
    emails_total = emails_q.scalar_one()

    return JobStats(
        id=job.id,
        name=job.name,
        status=job.status,
        total_sites=job.total_sites,
        pending=counts.get("pending", 0),
        running=counts.get("running", 0),
        done=counts.get("done", 0),
        failed=counts.get("failed", 0),
        skipped=counts.get("skipped", 0),
        emails_total=emails_total,
    )


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "paused"
    await session.commit()
    return {"status": job.status}


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> dict:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "running"
    await session.commit()
    await arq.enqueue_job("scrape_job", job_id, _job_id=f"job-resume-{job_id}")
    return {"status": job.status}


@router.post("/{job_id}/stop")
async def stop_job(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "stopped"
    await session.execute(
        update(Site).where(Site.job_id == job_id, Site.status == "pending").values(
            status="skipped", error="Job stopped"
        )
    )
    await session.commit()
    return {"status": job.status}


@router.post("/{job_id}/retry-failed")
async def retry_failed(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    arq: ArqRedis = Depends(get_arq),
) -> dict:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    updated = await session.execute(
        update(Site)
        .where(Site.job_id == job_id, Site.status.in_(["failed", "skipped"]))
        .values(status="pending", error=None)
    )
    job.status = "running"
    await session.commit()
    await arq.enqueue_job("scrape_job", job_id, _job_id=f"job-retry-{job_id}")
    return {"requeued": updated.rowcount or 0}


@router.delete("/{job_id}")
async def delete_job(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    await session.execute(delete(Job).where(Job.id == job_id))
    await session.commit()
    return {"deleted": job_id}


@router.get("/{job_id}/sites", response_model=list[SiteRead])
async def list_sites(
    job_id: int,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[SiteRead]:
    q = select(Site).where(Site.job_id == job_id)
    if status:
        q = q.where(Site.status == status)
    q = q.order_by(Site.id).offset(offset).limit(limit)
    res = await session.execute(q)
    return [SiteRead.model_validate(s) for s in res.scalars().all()]


@router.get("/{job_id}/emails.csv")
async def export_emails_csv(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    res = await session.execute(
        select(Email, Site.url)
        .join(Site, Site.id == Email.site_id)
        .where(Email.job_id == job_id)
        .order_by(Email.id)
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "site", "source_page", "found_at"])
    for email, site_url in res.all():
        writer.writerow([email.email, site_url, email.source_page, email.found_at.isoformat()])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_emails.csv"'},
    )
