from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.llm.base import LLMMessage


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def generate_json(
        self,
        messages: list[LLMMessage],
        schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> dict[str, Any]:
        _ = schema
        text = await self.generate_text(messages, temperature=temperature, max_tokens=max_tokens)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "steps": [
                    "Inspect service logs",
                    "Correlate with deploy timeline",
                    "Propose rollback with verification",
                ]
            }

