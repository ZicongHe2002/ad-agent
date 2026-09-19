from __future__ import annotations

from app.core.config import get_settings
from app.domain.enums import RunMode

from .openai_provider import OpenAIResponsesProvider
from .provider import LLMProvider, LLMProviderUnavailableError


def build_llm_provider(mode: RunMode | str = RunMode.NORMAL) -> LLMProvider | None:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    if provider == "mock":
        return None
    if provider != "openai":
        raise LLMProviderUnavailableError(f"Unsupported LLM provider: {provider}")
    fast = str(getattr(mode, "value", mode)) in {"FAST", "FIRST_COMMENT", "TOP5_COMMENT"}
    return OpenAIResponsesProvider(
        api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else "",
        model=settings.llm_model_fast if fast else settings.llm_model_normal,
        api_base=settings.llm_api_base,
        timeout_seconds=settings.llm_timeout_seconds,
    )
