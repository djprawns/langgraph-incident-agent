from __future__ import annotations

from typing import Any

from app.llm.base import LLMMessage


class MockProvider:
    name = "mock"

    async def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        _ = (messages, temperature, max_tokens)
        return "Mock text response"

    async def generate_json(
        self,
        messages: list[LLMMessage],
        schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> dict[str, Any]:
        _ = (messages, schema, temperature, max_tokens)
        return {
            "steps": [
                "Inspect signals and scope the incident",
                "Correlate root-cause evidence",
                "Recommend lowest-risk remediation",
            ]
        }

