from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMMessage:
    role: str
    content: str


class LLMProvider(Protocol):
    name: str

    async def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        ...

    async def generate_json(
        self,
        messages: list[LLMMessage],
        schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> dict[str, Any]:
        ...

