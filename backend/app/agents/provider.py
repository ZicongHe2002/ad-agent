"""LLM provider contract plus a deterministic, network-free test provider."""

from __future__ import annotations

import hashlib
import inspect
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    role: MessageRole
    content: str


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    request_id: str
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMCall(BaseModel):
    messages: list[LLMMessage]
    temperature: float
    timeout_seconds: float
    response_model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderError(RuntimeError):
    pass


class LLMProviderUnavailableError(LLMProviderError):
    pass


class LLMProvider(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[LLMMessage | Mapping[str, Any]],
        *,
        response_model: type[BaseModel] | None = None,
        temperature: float = 0.0,
        timeout_seconds: float = 10.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_model: type[BaseModel] | None = None,
        temperature: float = 0.0,
        timeout_seconds: float = 10.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        messages: list[LLMMessage] = []
        if system_prompt:
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system_prompt))
        messages.append(LLMMessage(role=MessageRole.USER, content=prompt))
        return await self.complete(
            messages,
            response_model=response_model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            metadata=metadata,
        )

    async def generate_structured(self, *args: Any, **kwargs: Any) -> Any:
        from .structured_output import generate_structured

        return await generate_structured(self, *args, **kwargs)


def _message(value: LLMMessage | Mapping[str, Any]) -> LLMMessage:
    return value if isinstance(value, LLMMessage) else LLMMessage(**dict(value))


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else value.dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _default_for_annotation(annotation: Any) -> Any:
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin in (list, list, Sequence, tuple, set, frozenset):
        return []
    if origin in (dict, dict, Mapping):
        return {}
    if origin is not None and args:
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1:
            return _default_for_annotation(non_none[0])
    try:
        if inspect.isclass(annotation) and issubclass(annotation, Enum):
            return next(iter(annotation)).value
    except TypeError:
        pass
    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is str:
        return ""
    return None


def _default_payload(model: type[BaseModel] | None) -> dict[str, Any]:
    if model is None:
        return {"ok": True}
    fields = getattr(model, "model_fields", None) or getattr(model, "__fields__", {})
    result: dict[str, Any] = {}
    for name, field in fields.items():
        default = getattr(field, "default", None)
        if default is not None and repr(default) not in {"PydanticUndefined", "Undefined"}:
            result[name] = _jsonable(default)
            continue
        factory = getattr(field, "default_factory", None)
        if factory is not None:
            result[name] = _jsonable(factory())
            continue
        annotation = getattr(field, "annotation", None) or getattr(field, "outer_type_", Any)
        result[name] = _default_for_annotation(annotation)
    return result


class MockLLMProvider(LLMProvider):
    """A deterministic provider with FIFO fixtures and complete call capture.

    A fixture can be a JSON-compatible value, Pydantic model, string, exception,
    or callable receiving the captured :class:`LLMCall`.  No network is used.
    """

    provider_name = "mock"
    model_name = "mock-deterministic-v1"

    def __init__(
        self,
        responses: Iterable[Any] | None = None,
        *,
        response: Any = None,
        default_response: Any = None,
        response_factory: Callable[[LLMCall], Any] | None = None,
    ) -> None:
        self._responses = list(responses or ())
        if response is not None:
            self._responses.insert(0, response)
        self._default_response = default_response
        self._response_factory = response_factory
        self.calls: list[LLMCall] = []

    def enqueue(self, *responses: Any) -> None:
        self._responses.extend(responses)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def complete(
        self,
        messages: Sequence[LLMMessage | Mapping[str, Any]],
        *,
        response_model: type[BaseModel] | None = None,
        temperature: float = 0.0,
        timeout_seconds: float = 10.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        normalized = [_message(item) for item in messages]
        call = LLMCall(
            messages=normalized,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            response_model_name=response_model.__name__ if response_model else None,
            metadata=dict(metadata or {}),
        )
        self.calls.append(call)
        if self._responses:
            selected = self._responses.pop(0)
        elif self._response_factory is not None:
            selected = self._response_factory(call)
        elif self._default_response is not None:
            selected = self._default_response
        else:
            selected = _default_payload(response_model)
        if callable(selected):
            selected = selected(call)
        if inspect.isawaitable(selected):
            selected = await selected
        if isinstance(selected, BaseException):
            raise selected
        if isinstance(selected, LLMResponse):
            return selected
        if isinstance(selected, str):
            content = selected
        else:
            content = json.dumps(
                _jsonable(selected),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        message_material = "\x1e".join(f"{item.role.value}:{item.content}" for item in normalized)
        digest = hashlib.sha256(
            f"{len(self.calls)}\x1f{message_material}\x1f{content}".encode()
        ).hexdigest()[:20]
        return LLMResponse(
            content=content,
            provider=self.provider_name,
            model=self.model_name,
            request_id=f"mock-{digest}",
            raw={"deterministic": True, "call_index": len(self.calls)},
        )


__all__ = [
    "LLMCall",
    "LLMMessage",
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderUnavailableError",
    "LLMResponse",
    "MessageRole",
    "MockLLMProvider",
]
