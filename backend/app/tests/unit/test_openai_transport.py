import json

import httpx
import pytest
from pydantic import BaseModel

from app.agents.factory import build_llm_provider
from app.agents.openai_provider import OpenAIResponsesProvider
from app.agents.provider import LLMMessage, LLMProviderUnavailableError, MessageRole
from app.core.config import get_settings


class Answer(BaseModel):
    text: str
    valid: bool = False


async def test_responses_transport_requests_strict_schema_and_returns_actual_provenance():
    async def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://llm.example/v1/responses"
        assert request.headers["authorization"] == "Bearer test-key"
        assert body["store"] is False
        schema = body["text"]["format"]["schema"]
        assert schema["required"] == ["text", "valid"]
        assert schema["additionalProperties"] is False
        assert "default" not in schema["properties"]["valid"]
        return httpx.Response(200, json={
            "id": "response-fixture", "model": "configured-model-snapshot", "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"text":"ok","valid":true}'}]}],
        })
    provider = OpenAIResponsesProvider(api_key="test-key", model="configured-model", api_base="https://llm.example/v1", transport=httpx.MockTransport(handler))
    response = await provider.complete([LLMMessage(role=MessageRole.USER, content="Answer")], response_model=Answer)
    assert response.request_id == "response-fixture"
    assert response.model == "configured-model-snapshot"
    assert Answer.model_validate_json(response.content).valid


@pytest.mark.parametrize("response", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]},
    {"status": "completed", "output": []},
])
async def test_incomplete_refused_or_empty_response_never_generates_fallback_comment(response):
    provider = OpenAIResponsesProvider(api_key="test-key", model="configured-model", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)))
    with pytest.raises(LLMProviderUnavailableError):
        await provider.complete([])


def test_configured_provider_uses_requested_model_and_never_silently_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL_FAST", "configured-fast")
    monkeypatch.setenv("LLM_MODEL_NORMAL", "configured-normal")
    get_settings.cache_clear()
    try:
        assert build_llm_provider("FAST").model_name == "configured-fast"
        assert build_llm_provider("NORMAL").model_name == "configured-normal"
        monkeypatch.setenv("LLM_PROVIDER", "typo-provider")
        get_settings.cache_clear()
        with pytest.raises(LLMProviderUnavailableError):
            build_llm_provider()
    finally:
        get_settings.cache_clear()
