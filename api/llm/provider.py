"""
Swappable LLM provider. Set LLM_PROVIDER=deepseek or LLM_PROVIDER=anthropic.
The agent depends only on `LLMProvider.complete`, never on a vendor SDK.
"""
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()

REQUEST_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, messages: list, max_tokens: int = 1200) -> str:
        """Return the model's text reply."""


class DeepSeekProvider(LLMProvider):
    """Default — lowest cost. DeepSeek exposes an OpenAI-compatible API."""

    def __init__(self):
        from openai import OpenAI  # imported lazily so the SDK is only needed if used

        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set (LLM_PROVIDER=deepseek).")
        self.client = OpenAI(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=REQUEST_TIMEOUT,
            max_retries=2,
        )
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")

    def complete(self, system: str, messages: list, max_tokens: int = 1200) -> str:
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}] + messages,
            max_tokens=max_tokens,
            temperature=0.1,  # low = more deterministic = better for citations
        )
        return r.choices[0].message.content or ""


class ClaudeProvider(LLMProvider):
    """Enterprise swap — stronger reasoning, higher cost."""

    def __init__(self):
        from anthropic import Anthropic

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (LLM_PROVIDER=anthropic).")
        self.client = Anthropic(api_key=key, timeout=REQUEST_TIMEOUT, max_retries=2)
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def complete(self, system: str, messages: list, max_tokens: int = 1200) -> str:
        r = self.client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


_PROVIDERS = {"deepseek": DeepSeekProvider, "anthropic": ClaudeProvider}


def get_llm() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "deepseek").lower().strip()
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER '{name}'. Choose one of: {list(_PROVIDERS)}")
    return _PROVIDERS[name]()
