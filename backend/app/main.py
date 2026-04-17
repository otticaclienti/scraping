from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import blacklist, emails, jobs
from app.db import init_db
from app.queue import close_arq


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_arq()


app = FastAPI(title="Email Scraper", lifespan=lifespan)

app.include_router(jobs.router)
app.include_router(emails.router)
app.include_router(blacklist.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
