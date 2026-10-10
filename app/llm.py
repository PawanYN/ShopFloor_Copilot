"""The one place that talks to a language model. Ollama today; anything with the same shape later."""

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app import config


@dataclass
class ModelReply:
    data: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    seconds: float


class ModelTimeout(Exception):
    """The model did not answer within the time it was given."""


class ModelClient(Protocol):
    def chat_json(
        self, model: str, system: str, user: str, schema: dict[str, Any], timeout: float | None = None
    ) -> ModelReply: ...


class OllamaClient:
    def __init__(self, base_url: str = config.OLLAMA_URL, timeout: float = 600) -> None:
        self._base_url = base_url
        self._timeout = timeout

    def chat_json(
        self, model: str, system: str, user: str, schema: dict[str, Any], timeout: float | None = None
    ) -> ModelReply:
        started = time.perf_counter()
        if timeout is not None and timeout <= 0:
            raise ModelTimeout("no time left for the model")
        try:
            response = self._post(model, system, user, schema, timeout or self._timeout)
        except httpx.TimeoutException as error:
            raise ModelTimeout(str(error) or "the model took too long") from error
        response.raise_for_status()
        body = response.json()
        return ModelReply(
            data=json.loads(body["message"]["content"]),
            prompt_tokens=body.get("prompt_eval_count", 0),
            completion_tokens=body.get("eval_count", 0),
            seconds=round(time.perf_counter() - started, 2),
        )

    def _post(self, model: str, system: str, user: str, schema: dict[str, Any], timeout: float) -> httpx.Response:
        return httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "format": schema,
                "stream": False,
                # Zero randomness and a fixed seed: the same input gives the same answer (decision 3.8).
                "options": {"temperature": 0, "seed": 0, "num_ctx": config.MODEL_CONTEXT_TOKENS},
            },
            timeout=timeout,
        )
