from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Email, Site
from app.schemas import EmailRead

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("", response_model=list[EmailRead])
async def list_emails(
    job_id: int | None = None,
    site_id: int | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[EmailRead]:
    query = select(Email)
    if job_id is not None:
        query = query.where(Email.job_id == job_id)
    if site_id is not None:
        query = query.where(Email.site_id == site_id)
    if q:
        query = query.where(Email.email.ilike(f"%{q.lower()}%"))
    query = query.order_by(Email.id.desc()).offset(offset).limit(limit)
    res = await session.execute(query)
    return [EmailRead.model_validate(e) for e in res.scalars().all()]


@router.get("/count")
async def count_emails(
    job_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    q = select(func.count()).select_from(Email)
    if job_id is not None:
        q = q.where(Email.job_id == job_id)
    total = (await session.execute(q)).scalar_one()

    distinct_q = select(func.count(func.distinct(Email.email)))
    if job_id is not None:
        distinct_q = distinct_q.where(Email.job_id == job_id)
    distinct = (await session.execute(distinct_q)).scalar_one()

    return {"total": total, "distinct": distinct}
