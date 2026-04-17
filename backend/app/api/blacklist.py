from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import BlacklistDomain
from app.schemas import BlacklistCreate, BlacklistRead

router = APIRouter(prefix="/blacklist", tags=["blacklist"])


@router.get("", response_model=list[BlacklistRead])
async def list_blacklist(session: AsyncSession = Depends(get_session)) -> list[BlacklistRead]:
    res = await session.execute(select(BlacklistDomain).order_by(BlacklistDomain.domain))
    return [BlacklistRead.model_validate(d) for d in res.scalars().all()]


@router.post("", response_model=BlacklistRead)
async def add_blacklist(
    payload: BlacklistCreate, session: AsyncSession = Depends(get_session)
) -> BlacklistRead:
    domain = payload.domain.strip().lower()
    if not domain:
        raise HTTPException(400, "Empty domain")
    existing = await session.execute(
        select(BlacklistDomain).where(BlacklistDomain.domain == domain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Already blacklisted")
    bd = BlacklistDomain(domain=domain)
    session.add(bd)
    await session.commit()
    await session.refresh(bd)
    return BlacklistRead.model_validate(bd)


@router.delete("/{domain}")
async def remove_blacklist(
    domain: str, session: AsyncSession = Depends(get_session)
) -> dict:
    await session.execute(delete(BlacklistDomain).where(BlacklistDomain.domain == domain.lower()))
    await session.commit()
    return {"deleted": domain}
