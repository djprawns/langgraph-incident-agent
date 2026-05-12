from __future__ import annotations

import os

from app.llm.factory import build_llm
from app.settings import Settings


def test_factory_mock_backend() -> None:
    os.environ["LLM_BACKEND"] = "mock"
    settings = Settings()
    provider = build_llm(settings)
    assert provider.name == "mock"

