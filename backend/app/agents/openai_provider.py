"""Responses API transport. Local policy and structured validation remain authoritative."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx
from pydantic import BaseModel

from .provider import LLMMessage, LLMProvider, LLMProviderUnavailableError, LLMResponse


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: visit(item) for key, item in value.items() if key != "default"}
        if result.get("type") == "object":
            result["additionalProperties"] = False
            result["required"] = list(result.get("properties", {}))
        return result

    return dict(visit(model.model_json_schema()))


class OpenAIResponsesProvider(LLMProvider):
    provider_name = "openai"

    def __init__(
        self, *, api_key: str, model: str, api_base: str = "https://api.openai.com/v1",
        timeout_seconds: float = 5.0, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip() or model.startswith("mock-"):
            raise LLMProviderUnavailableError("A real LLM API key and model must be configured")
        url = httpx.URL(api_base)
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
            raise LLMProviderUnavailableError("LLM_API_BASE must be an HTTPS API root")
        self._api_key = api_key
        self.model_name = model
        self._url = api_base.rstrip("/") + "/responses"
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    async def complete(
        self, messages: Sequence[LLMMessage | Mapping[str, Any]], *,
        response_model: type[BaseModel] | None = None, temperature: float = 0.0,
        timeout_seconds: float = 10.0, metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        # Sampling controls differ between model families. Let the selected model
        # use its supported defaults rather than blindly sending temperature.
        del temperature, metadata
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": [
                (item if isinstance(item, LLMMessage) else LLMMessage(**dict(item))).model_dump(mode="json")
                for item in messages
            ],
            "store": False,
        }
        if response_model is not None:
            payload["text"] = {"format": {
                "type": "json_schema", "name": response_model.__name__,
                "strict": True, "schema": strict_json_schema(response_model),
            }}
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=min(timeout_seconds, self.timeout_seconds),
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self._url, json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Do not surface provider request bodies, credentials, or raw errors.
            raise LLMProviderUnavailableError("LLM request failed") from exc
        if not isinstance(data, dict) or data.get("status") != "completed":
            raise LLMProviderUnavailableError("LLM response did not complete")
        parts: list[str] = []
        output = data.get("output")
        if not isinstance(output, list):
            raise LLMProviderUnavailableError("LLM returned an invalid response")
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise LLMProviderUnavailableError("LLM declined this generation")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    parts.append(part["text"])
        if not parts:
            raise LLMProviderUnavailableError("LLM response contains no text")
        return LLMResponse(
            content="".join(parts), provider=self.provider_name,
            model=str(data.get("model") or self.model_name),
            request_id=str(data.get("id") or response.headers.get("x-request-id") or "unknown"),
        )
