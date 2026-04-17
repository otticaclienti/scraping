from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobConfig(BaseModel):
    concurrency: int = Field(default=50, ge=1, le=500)
    timeout_seconds: int = Field(default=15, ge=3, le=120)
    max_pages_per_site: int = Field(default=8, ge=1, le=50)
    max_attempts: int = Field(default=2, ge=1, le=5)
    render_js_fallback: bool = True
    verify_mx: bool = False
    follow_sitemap: bool = True
    user_agent: str | None = None


class JobCreate(BaseModel):
    name: str
    config: JobConfig = Field(default_factory=JobConfig)
    urls: list[str]


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    config: dict[str, Any]
    total_sites: int
    created_at: datetime
    updated_at: datetime


class JobStats(BaseModel):
    id: int
    name: str
    status: str
    total_sites: int
    pending: int
    running: int
    done: int
    failed: int
    skipped: int
    emails_total: int


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    url: str
    status: str
    attempts: int
    emails_found: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class EmailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    job_id: int
    email: str
    source_page: str
    found_at: datetime


class BlacklistCreate(BaseModel):
    domain: str


class BlacklistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    created_at: datetime
