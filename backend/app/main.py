import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import Base, SessionLocal, engine, ensure_columns
from .routers import admin, drafts, evaluation, ledger
from .seed import ensure_seeded

log = logging.getLogger("brandsentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    added = ensure_columns(engine)
    if added:
        log.info("Added database columns: %s", ", ".join(added))
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            if ensure_seeded(db):
                log.info("Seeded the Nimbus Pay demo brand.")
        finally:
            db.close()
    if settings.ocr_warmup:
        from .services import images

        threading.Thread(target=images.warm_up, name="ocr-warmup", daemon=True).start()
    if settings.recover_reviews:
        threading.Thread(target=drafts.recover_pending_reviews, name="review-recovery", daemon=True).start()
    yield


class CatchErrors:
    """Sits inside CORS, so an unexpected error reaches the browser as a readable JSON error (with CORS headers),
    not as what looks like a network failure."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracked(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception:
            log.exception("Unhandled error on %s", scope.get("path"))
            if not started:
                await JSONResponse({"detail": "Something went wrong on the server. Please try again."},
                                   status_code=500)(scope, receive, send)


app = FastAPI(title="BrandSentinel API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def readable_validation_error(_request, exc: RequestValidationError):
    first = exc.errors()[0]
    where = str(first["loc"][-1]).replace("_", " ")
    return JSONResponse({"detail": f"Invalid {where}: {first['msg'].lower()}."}, status_code=422)


app.add_middleware(CatchErrors)
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
