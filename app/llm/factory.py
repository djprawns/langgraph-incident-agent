from __future__ import annotations

from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAIProvider
from app.settings import Settings


def build_llm(settings: Settings):
    backend = settings.llm_backend.lower().strip()

    if backend == "mock":
        return MockProvider()
    if backend == "ollama":
        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url)
    if backend == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_BACKEND=openai")
        return OpenAIProvider(model=settings.openai_model, api_key=settings.openai_api_key)

    raise ValueError(f"Unsupported LLM_BACKEND: {settings.llm_backend}")

