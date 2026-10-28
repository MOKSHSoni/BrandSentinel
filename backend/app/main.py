import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import admin, drafts, evaluation, ledger
from .seed import ensure_seeded

log = logging.getLogger("brandsentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            if ensure_seeded(db):
                log.info("Seeded the Nimbus Pay demo brand.")
        finally:
            db.close()
    yield


app = FastAPI(title="BrandSentinel API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin.router)
app.include_router(drafts.router)
app.include_router(ledger.router)
app.include_router(evaluation.router)


@app.get("/")
def root():
    return {"service": "BrandSentinel API", "docs": "/docs", "health": "/api/health"}
