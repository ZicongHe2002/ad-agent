"""Strict structured-output validation with one and only one repair attempt."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .provider import LLMMessage, LLMProvider, LLMResponse, MessageRole

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredOutputError(ValueError):
    def __init__(self, message: str, *, attempts: int, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.errors = list(errors or ())


class StructuredOutputResult(BaseModel, Generic[ModelT]):
    value: ModelT
    response: LLMResponse
    attempts: int
    repaired: bool


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)


def _extract_json(content: str) -> Any:
    text = content.strip()
    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as direct_error:
        decoder = json.JSONDecoder()
        starts = [index for index, character in enumerate(text) if character in "[{"]
        for start in starts:
            try:
                value, consumed = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            if text[start + consumed :].strip() in {"", "```"}:
                return value
        raise direct_error


def validate_structured_output(
    content: str | Mapping[str, Any] | BaseModel, model: type[ModelT]
) -> ModelT:
    if isinstance(content, model):
        return content
    if isinstance(content, BaseModel):
        payload = content.model_dump() if hasattr(content, "model_dump") else content.dict()
    elif isinstance(content, Mapping):
        payload = dict(content)
    else:
        payload = _extract_json(content)
    if hasattr(model, "model_validate"):
        return model.model_validate(payload)
    return model.parse_obj(payload)


def _validation_summary(exc: BaseException) -> str:
    if isinstance(exc, ValidationError):
        locations = []
        for item in exc.errors()[:8]:
            location = ".".join(str(part) for part in item.get("loc", ()))
            locations.append(f"{location or '<root>'}: {item.get('type', 'invalid')}")
        return "; ".join(locations)
    if isinstance(exc, json.JSONDecodeError):
        return f"invalid JSON at line {exc.lineno}, column {exc.colno}"
    return type(exc).__name__


async def generate_structured(
    provider: LLMProvider,
    messages: Sequence[LLMMessage | Mapping[str, Any]],
    *,
    response_model: type[ModelT],
    temperature: float = 0.0,
    timeout_seconds: float = 10.0,
    metadata: Mapping[str, Any] | None = None,
) -> StructuredOutputResult[ModelT]:
    """Generate, validate, then make at most one schema-repair call."""

    normalized = [
        item if isinstance(item, LLMMessage) else LLMMessage(**dict(item)) for item in messages
    ]
    response = await provider.complete(
        normalized,
        response_model=response_model,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        metadata=metadata,
    )
    errors: list[str] = []
    try:
        value = validate_structured_output(response.content, response_model)
        return StructuredOutputResult(value=value, response=response, attempts=1, repaired=False)
    except (ValueError, TypeError, ValidationError, json.JSONDecodeError) as exc:
        errors.append(_validation_summary(exc))

    repair_instruction = (
        "Return only valid JSON matching the requested schema. Preserve the intended "
        "meaning, add no commentary, and do not add fields outside the schema. "
        f"Validation issue: {errors[-1]}. Invalid output follows:\n{response.content}"
    )
    repair_messages = list(normalized)
    repair_messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=response.content))
    repair_messages.append(LLMMessage(role=MessageRole.USER, content=repair_instruction))
    repaired_response = await provider.complete(
        repair_messages,
        response_model=response_model,
        temperature=0.0,
        timeout_seconds=timeout_seconds,
        metadata={**dict(metadata or {}), "structured_output_repair": True, "repair_attempt": 1},
    )
    try:
        value = validate_structured_output(repaired_response.content, response_model)
        return StructuredOutputResult(
            value=value, response=repaired_response, attempts=2, repaired=True
        )
    except (ValueError, TypeError, ValidationError, json.JSONDecodeError) as exc:
        errors.append(_validation_summary(exc))
        raise StructuredOutputError(
            "Structured output remained invalid after one repair attempt",
            attempts=2,
            errors=errors,
        ) from exc


__all__ = [
    "StructuredOutputError",
    "StructuredOutputResult",
    "generate_structured",
    "validate_structured_output",
]
