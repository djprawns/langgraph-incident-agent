from __future__ import annotations

import json
from typing import Any

import httpx

from app.llm.base import LLMMessage


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return data.get("message", {}).get("content", "")

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

