"""Static facts about the free-tier providers AIVA can use (researched Nov 2026).

Per-model limits live in ``config/aiva.yaml`` so they can be tuned without code
changes; this module only holds what the dashboard needs to help you sign up and
what the doctor needs to verify a key.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    name: str
    label: str
    key_env: str
    signup_url: str
    #: OpenAI-style ``GET {models_url}`` used by the doctor to validate keys and model ids.
    models_url: str
    free_tier: str
    #: The default request-window for rate-limit headers that don't name one.
    header_request_window: str = "day"
    header_token_window: str = "minute"


PROVIDERS: dict[str, ProviderInfo] = {
    "groq": ProviderInfo(
        name="groq",
        label="Groq",
        key_env="GROQ_API_KEY",
        signup_url="https://console.groq.com/keys",
        models_url="https://api.groq.com/openai/v1/models",
        free_tier="Fastest. gpt-oss-120b / gpt-oss-20b / qwen3.8-27b: 30 RPM, 1K req/day, 8K TPM each "
        "(cached tokens free). Whisper STT: 2K req/day.",
    ),
    "mistral": ProviderInfo(
        name="mistral",
        label="Mistral",
        key_env="MISTRAL_API_KEY",
        signup_url="https://console.mistral.ai/api-keys",
        models_url="https://api.mistral.ai/v1/models",
        free_tier="Experiment plan: 1 req/s, 500K tokens/min, very large monthly budget. "
        "Phone verification; data may be used for training.",
        header_request_window="minute",
    ),
    "google": ProviderInfo(
        name="google",
        label="Google Gemini",
        key_env="GEMINI_API_KEY",
        signup_url="https://aistudio.google.com/apikey",
        models_url="https://generativelanguage.googleapis.com/v1beta/openai/models",
        free_tier="Flash-Lite ≈ 10 RPM / 500 req/day, Flash ≈ 20 req/day (free tier, Nov 2026).",
    ),
    "cerebras": ProviderInfo(
        name="cerebras",
        label="Cerebras",
        key_env="CEREBRAS_API_KEY",
        signup_url="https://cloud.cerebras.ai",
        models_url="https://api.cerebras.ai/v1/models",
        free_tier="No permanent free tier: $5 trial credit (30 days) after adding a card. "
        "qwen-3.8-27b: 300 RPM, 150K TPM.",
    ),
    "openrouter": ProviderInfo(
        name="openrouter",
        label="OpenRouter",
        key_env="OPENROUTER_API_KEY",
        signup_url="https://openrouter.ai/keys",
        models_url="https://openrouter.ai/api/v1/models",
        free_tier=":free models: 20 RPM, 50 req/day (1000/day after $10 lifetime top-up).",
    ),
}
