from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.runs import router as runs_router
from app.logging_config import configure_logging
from app.settings import Settings

settings = Settings()
configure_logging(log_level=settings.log_level, log_file=settings.log_file)
logger = logging.getLogger(__name__)
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    logger.info("request.start method=%s path=%s", request.method, request.url.path)
    response = await call_next(request)
    logger.info(
        "request.end method=%s path=%s status=%s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "llm_backend": settings.llm_backend}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")

