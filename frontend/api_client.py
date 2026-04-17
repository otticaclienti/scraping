from __future__ import annotations

import os
from typing import Any

import httpx

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND_URL, timeout=30.0)


def list_jobs() -> list[dict]:
    with _client() as c:
        r = c.get("/jobs")
        r.raise_for_status()
        return r.json()


def job_stats(job_id: int) -> dict:
    with _client() as c:
        r = c.get(f"/jobs/{job_id}")
        r.raise_for_status()
        return r.json()


def create_job(
    name: str,
    config: dict[str, Any],
    urls_text: str = "",
    file_bytes: bytes | None = None,
    filename: str | None = None,
) -> dict:
    import json

    data = {"name": name, "config_json": json.dumps(config), "urls_text": urls_text}
    files = None
    if file_bytes is not None and filename:
        files = {"file": (filename, file_bytes, "text/plain")}
    with _client() as c:
        r = c.post("/jobs", data=data, files=files)
        r.raise_for_status()
        return r.json()


def pause_job(job_id: int) -> dict:
    with _client() as c:
        r = c.post(f"/jobs/{job_id}/pause")
        r.raise_for_status()
        return r.json()


def resume_job(job_id: int) -> dict:
    with _client() as c:
        r = c.post(f"/jobs/{job_id}/resume")
        r.raise_for_status()
        return r.json()


def stop_job(job_id: int) -> dict:
    with _client() as c:
        r = c.post(f"/jobs/{job_id}/stop")
        r.raise_for_status()
        return r.json()


def retry_failed(job_id: int) -> dict:
    with _client() as c:
        r = c.post(f"/jobs/{job_id}/retry-failed")
        r.raise_for_status()
        return r.json()


def delete_job(job_id: int) -> dict:
    with _client() as c:
        r = c.delete(f"/jobs/{job_id}")
        r.raise_for_status()
        return r.json()


def list_sites(job_id: int, status: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    with _client() as c:
        r = c.get(f"/jobs/{job_id}/sites", params=params)
        r.raise_for_status()
        return r.json()


def list_emails(
    job_id: int | None = None,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if job_id is not None:
        params["job_id"] = job_id
    if q:
        params["q"] = q
    with _client() as c:
        r = c.get("/emails", params=params)
        r.raise_for_status()
        return r.json()


def count_emails(job_id: int | None = None) -> dict:
    params: dict[str, Any] = {}
    if job_id is not None:
        params["job_id"] = job_id
    with _client() as c:
        r = c.get("/emails/count", params=params)
        r.raise_for_status()
        return r.json()


def export_csv_url(job_id: int) -> str:
    return f"{BACKEND_URL}/jobs/{job_id}/emails.csv"


def fetch_csv(job_id: int) -> bytes:
    with _client() as c:
        r = c.get(f"/jobs/{job_id}/emails.csv")
        r.raise_for_status()
        return r.content


def list_blacklist() -> list[dict]:
    with _client() as c:
        r = c.get("/blacklist")
        r.raise_for_status()
        return r.json()


def add_blacklist(domain: str) -> dict:
    with _client() as c:
        r = c.post("/blacklist", json={"domain": domain})
        r.raise_for_status()
        return r.json()


def remove_blacklist(domain: str) -> dict:
    with _client() as c:
        r = c.delete(f"/blacklist/{domain}")
        r.raise_for_status()
        return r.json()
