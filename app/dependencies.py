from __future__ import annotations

from app.llm.factory import build_llm
from app.services.runtime import GraphRuntime
from app.settings import Settings

_runtime_singleton: GraphRuntime | None = None


def get_runtime() -> GraphRuntime:
    global _runtime_singleton
    if _runtime_singleton is None:
        settings = Settings()
        llm = build_llm(settings)
        _runtime_singleton = GraphRuntime(llm=llm, db_url=settings.sqlite_db_url)
    return _runtime_singleton

