from __future__ import annotations

from enum import Enum
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agents.provider import (
    LLMCall,
    LLMMessage,
    LLMResponse,
    MessageRole,
    MockLLMProvider,
)
from app.agents.structured_output import (
    StructuredOutputError,
    generate_structured,
    validate_structured_output,
)


class Tone(str, Enum):
    WARM = "warm"
    DIRECT = "direct"


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    score: int


class OtherReply(BaseModel):
    text: str
    score: int


class DefaultPayload(BaseModel):
    enabled: bool
    count: int
    ratio: float
    label: str
    tags: list[str]
    attributes: dict[str, int]
    tone: Tone
    optional_count: int | None
    stable: str = "ready"
    generated: list[str] = Field(default_factory=lambda: ["fixture"])


@pytest.mark.parametrize(
    "payload",
    [
        '{"text":"grounded","score":7}',
        '```json\n{"text":"grounded","score":7}\n```',
        'result: {"text":"grounded","score":7}',
        {"text": "grounded", "score": 7},
        OtherReply(text="grounded", score=7),
    ],
)
def test_validate_structured_output_accepts_supported_payloads(payload: Any) -> None:
    result = validate_structured_output(payload, Reply)
    assert result == Reply(text="grounded", score=7)


def test_validate_structured_output_returns_existing_model_instance() -> None:
    result = Reply(text="already valid", score=9)
    assert validate_structured_output(result, Reply) is result


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"text":"missing score"}',
        '{"text":"ok","score":1,"extra":true}',
    ],
)
def test_validate_structured_output_rejects_invalid_content(content: str) -> None:
    with pytest.raises(ValueError):
        validate_structured_output(content, Reply)


@pytest.mark.asyncio
async def test_generate_structured_succeeds_without_repair() -> None:
    provider = MockLLMProvider(response={"text": "specific", "score": 8})
    result = await generate_structured(
        provider,
        [{"role": "user", "content": "Draft a reply"}],
        response_model=Reply,
        temperature=0.3,
        timeout_seconds=4,
        metadata={"job": "one"},
    )

    assert result.value == Reply(text="specific", score=8)
    assert (result.attempts, result.repaired) == (1, False)
    assert provider.call_count == 1
    assert provider.calls[0].temperature == 0.3
    assert provider.calls[0].metadata == {"job": "one"}


@pytest.mark.asyncio
async def test_generate_structured_repairs_once_with_safe_settings() -> None:
    provider = MockLLMProvider(
        responses=['{"text":"missing score"}', {"text": "repaired", "score": 6}]
    )
    result = await generate_structured(
        provider,
        [LLMMessage(role=MessageRole.USER, content="Draft")],
        response_model=Reply,
        temperature=0.8,
        metadata={"job": "two"},
    )

    assert result.value.text == "repaired"
    assert (result.attempts, result.repaired) == (2, True)
    repair_call = provider.calls[1]
    assert repair_call.temperature == 0.0
    assert repair_call.messages[-2].role == MessageRole.ASSISTANT
    assert "missing score" in repair_call.messages[-2].content
    assert repair_call.metadata == {
        "job": "two",
        "structured_output_repair": True,
        "repair_attempt": 1,
    }


@pytest.mark.asyncio
async def test_generate_structured_raises_after_exactly_one_failed_repair() -> None:
    provider = MockLLMProvider(responses=["not json", '{"text":"still incomplete"}'])

    with pytest.raises(StructuredOutputError) as captured:
        await generate_structured(provider, [], response_model=Reply)

    assert provider.call_count == 2
    assert captured.value.attempts == 2
    assert len(captured.value.errors) == 2
    assert captured.value.errors[0].startswith("invalid JSON")
    assert captured.value.errors[1].startswith("score:")


@pytest.mark.asyncio
async def test_provider_generate_builds_system_and_user_messages() -> None:
    provider = MockLLMProvider(default_response="plain response")
    response = await provider.generate(
        "User prompt",
        system_prompt="System prompt",
        temperature=0.25,
        timeout_seconds=3,
        metadata={"trace": "abc"},
    )

    assert response.content == "plain response"
    assert [message.role for message in provider.calls[0].messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    assert provider.calls[0].timeout_seconds == 3


@pytest.mark.asyncio
async def test_provider_generate_omits_empty_system_message() -> None:
    provider = MockLLMProvider(response="ok")
    await provider.generate("Only user")
    assert [message.role for message in provider.calls[0].messages] == [MessageRole.USER]


@pytest.mark.asyncio
async def test_provider_generate_structured_delegates_to_validator() -> None:
    provider = MockLLMProvider(response={"text": "delegated", "score": 5})
    result = await provider.generate_structured(
        [{"role": MessageRole.USER, "content": "Draft"}],
        response_model=Reply,
    )
    assert result.value.text == "delegated"


@pytest.mark.asyncio
async def test_mock_provider_constructs_valid_default_model_payload() -> None:
    provider = MockLLMProvider()
    response = await provider.complete([], response_model=DefaultPayload)
    parsed = DefaultPayload.model_validate_json(response.content)

    assert parsed == DefaultPayload(
        enabled=False,
        count=0,
        ratio=0.0,
        label="",
        tags=[],
        attributes={},
        tone=Tone.WARM,
        optional_count=None,
        stable="ready",
        generated=["fixture"],
    )
    assert provider.calls[0].response_model_name == "DefaultPayload"


@pytest.mark.asyncio
async def test_mock_provider_default_without_schema_is_json() -> None:
    response = await MockLLMProvider().complete([])
    assert response.content == '{"ok":true}'


@pytest.mark.asyncio
async def test_mock_provider_serializes_models_enums_and_collections() -> None:
    class Container(BaseModel):
        tone: Tone
        values: tuple[int, ...]

    provider = MockLLMProvider(response=Container(tone=Tone.DIRECT, values=(1, 2)))
    response = await provider.complete([])
    assert response.content == '{"tone":"direct","values":[1,2]}'


@pytest.mark.asyncio
async def test_mock_provider_uses_fifo_enqueue_callable_and_async_factory() -> None:
    async def async_response(call: LLMCall) -> dict[str, object]:
        return {"text": call.messages[0].content, "score": 3}

    provider = MockLLMProvider(responses=[lambda _call: "first"])
    provider.enqueue(async_response)

    first = await provider.complete([{"role": "user", "content": "ignored"}])
    second = await provider.complete([{"role": "user", "content": "from call"}])
    assert first.content == "first"
    assert second.content == '{"score":3,"text":"from call"}'


@pytest.mark.asyncio
async def test_mock_provider_response_factory_and_default_response_precedence() -> None:
    provider = MockLLMProvider(
        default_response="default",
        response_factory=lambda call: f"factory:{call.temperature}",
    )
    response = await provider.complete([], temperature=0.4)
    assert response.content == "factory:0.4"


@pytest.mark.asyncio
async def test_mock_provider_raises_fixture_exception_and_passes_response_through() -> None:
    expected = LLMResponse(
        content="raw",
        provider="fixture",
        model="fixture-v1",
        request_id="fixture-id",
    )
    provider = MockLLMProvider(responses=[RuntimeError("offline"), expected])

    with pytest.raises(RuntimeError, match="offline"):
        await provider.complete([])
    assert await provider.complete([]) is expected


@pytest.mark.asyncio
async def test_mock_provider_request_ids_are_deterministic_per_call() -> None:
    first_provider = MockLLMProvider(response={"b": 2, "a": 1})
    second_provider = MockLLMProvider(response={"a": 1, "b": 2})
    messages = [{"role": "user", "content": "same"}]

    first = await first_provider.complete(messages)
    second = await second_provider.complete(messages)
    assert first.content == second.content == '{"a":1,"b":2}'
    assert first.request_id == second.request_id
    assert first.raw == {"deterministic": True, "call_index": 1}
