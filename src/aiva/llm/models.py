"""Build pydantic-ai models for each deployment, wired into the QuotaGuard.

Each deployment gets its *own* HTTP client whose response hook feeds rate-limit
headers to the quota guard, and is wrapped in :class:`GuardedModel`, which

* refuses instantly (no network round-trip) when the quota guard says the
  deployment is exhausted or cooling down — so the fallback chain moves on in
  microseconds instead of waiting for a 429, and
* records usage, latency and failures for the dashboard and the warnings.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import httpx2
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelHTTPError,
    ModelQuotaExceededError,
    ModelRateLimitError,
)
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from ..config import DeploymentConfig, LLMConfig, Secrets
from ..text import estimate_tokens
from .quota import FailureKind, QuotaGuard

_TIMEOUT = 30.0


class QuotaSkip(ModelRateLimitError):
    """Raised before any network call when the quota guard rules a deployment out."""


def estimate_request_tokens(
    messages: list[ModelMessage], params: ModelRequestParameters | None = None
) -> int:
    """Cheap upper-bound-ish estimate of a request's prompt size (text + tool schemas)."""
    total = 0
    for message in messages:
        for part in getattr(message, "parts", ()):
            content = getattr(part, "content", None)
            if isinstance(content, str):
                total += estimate_tokens(content)
            elif content is not None:
                total += estimate_tokens(str(content))
            args = getattr(part, "args", None)
            if args:
                total += estimate_tokens(args if isinstance(args, str) else json.dumps(args))
        instructions = getattr(message, "instructions", None)
        if instructions:
            total += estimate_tokens(instructions)
    if params is not None:
        for tool in params.function_tools:
            total += estimate_tokens(tool.name + (tool.description or "")) + estimate_tokens(
                json.dumps(tool.parameters_json_schema)
            )
    return total


def classify_failure(exc: BaseException) -> tuple[FailureKind, float | None]:
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(exc, ModelRateLimitError | ModelQuotaExceededError):
        return "rate_limit", retry_after
    if isinstance(exc, ModelHTTPError):
        code = exc.status_code
        if code == 429:
            return "rate_limit", retry_after
        if code in (401, 403):
            return "auth", None
        if code in (400, 404, 422):
            return "bad_request", None
        return "server", retry_after
    if isinstance(exc, ModelConnectionError | TimeoutError):
        return "timeout", None
    if isinstance(exc, ModelAPIError):
        return "server", retry_after
    return "other", None


class GuardedModel(WrapperModel):
    def __init__(self, wrapped: Model, deployment: DeploymentConfig, quota: QuotaGuard) -> None:
        super().__init__(wrapped)
        self.deployment = deployment
        self.quota = quota

    @property
    def deployment_id(self) -> str:
        return self.deployment.id

    def _precheck(self, messages: list[ModelMessage], params: ModelRequestParameters) -> None:
        settings = getattr(self.wrapped, "settings", None) or {}
        # spoken replies are short: budget ~200 output tokens rather than the full max_tokens cap
        estimate = estimate_request_tokens(messages, params) + min(
            int(settings.get("max_tokens") or 400), 200
        )
        ok, reason = self.quota.fits(self.deployment_id, estimate)
        if not ok:
            raise QuotaSkip(model_name=self.model_name, message=f"{self.deployment_id} skipped: {reason}")

    async def _pace(self) -> None:
        delay = self.quota.pace_delay(self.deployment_id)
        if delay > 1.5:  # would stall the conversation: let the fallback chain move on
            raise QuotaSkip(model_name=self.model_name, message=f"{self.deployment_id} busy for {delay:.1f}s")
        if delay > 0:
            await asyncio.sleep(delay)
        self.quota.mark_request(self.deployment_id)

    def _record_failure(self, exc: BaseException) -> None:
        if isinstance(exc, QuotaSkip):
            return
        kind, retry_after = classify_failure(exc)
        self.quota.on_failure(self.deployment_id, kind, str(exc)[:200], retry_after)

    def _record_success(self, response_usage: Any, started: float) -> None:
        cached = int(getattr(response_usage, "cache_read_tokens", 0) or 0)
        input_tokens = int(getattr(response_usage, "input_tokens", 0) or 0) - cached
        output_tokens = int(getattr(response_usage, "output_tokens", 0) or 0)
        self.quota.on_success(
            self.deployment_id, input_tokens, output_tokens, (time.monotonic() - started) * 1000
        )

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self._precheck(messages, model_request_parameters)
        await self._pace()
        started = time.monotonic()
        try:
            response = await super().request(messages, model_settings, model_request_parameters)
        except Exception as exc:
            self._record_failure(exc)
            raise
        self._record_success(response.usage, started)
        return response

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any | None = None,
    ) -> AsyncGenerator[StreamedResponse]:
        self._precheck(messages, model_request_parameters)
        await self._pace()
        started = time.monotonic()
        try:
            async with super().request_stream(
                messages, model_settings, model_request_parameters, run_context
            ) as stream:
                yield stream
        except Exception as exc:
            self._record_failure(exc)
            raise
        self._record_success(stream.usage, started)


# ── factory ──────────────────────────────────────────────────────────────────

HeaderHook = Callable[[Any], Awaitable[None]]


def _header_hook(quota: QuotaGuard, dep_id: str) -> HeaderHook:
    async def on_response(response: Any) -> None:
        quota.on_headers(dep_id, response.status_code, response.headers)

    return on_response


def _model_settings(dep: DeploymentConfig, llm: LLMConfig) -> ModelSettings:
    settings: dict[str, Any] = {
        "max_tokens": llm.max_output_tokens,
        "temperature": llm.temperature,
        "max_retries": 0,  # never sit in SDK back-off: the fallback chain is faster
        "first_event_timeout": llm.first_token_timeout_s,
        "request_timeout": _TIMEOUT,
    }
    settings.update(dep.settings)
    return settings  # type: ignore[return-value]


def build_model(dep: DeploymentConfig, llm: LLMConfig, secrets: Secrets, quota: QuotaGuard) -> GuardedModel:
    """Create the provider-specific pydantic-ai model for one deployment."""
    api_key = secrets.key_for(dep.provider, dep.api_key_env)
    if not api_key:
        raise ValueError(f"no API key for {dep.provider}")
    hooks = {"response": [_header_hook(quota, dep.id)]}
    settings = _model_settings(dep, llm)

    model: Model
    if dep.provider == "groq":
        from pydantic_ai.models.groq import GroqModel
        from pydantic_ai.providers.groq import GroqProvider

        client = httpx.AsyncClient(event_hooks=hooks, timeout=httpx.Timeout(_TIMEOUT, connect=5.0))
        model = GroqModel(
            dep.model, provider=GroqProvider(api_key=api_key, http_client=client), settings=settings
        )
    elif dep.provider == "mistral":
        from pydantic_ai.models.mistral import MistralModel
        from pydantic_ai.providers.mistral import MistralProvider

        client2 = httpx2.AsyncClient(event_hooks=hooks, timeout=httpx2.Timeout(_TIMEOUT, connect=5.0))
        model = MistralModel(
            dep.model, provider=MistralProvider(api_key=api_key, http_client=client2), settings=settings
        )
    elif dep.provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        client2 = httpx2.AsyncClient(event_hooks=hooks, timeout=httpx2.Timeout(_TIMEOUT, connect=5.0))
        model = GoogleModel(
            dep.model, provider=GoogleProvider(api_key=api_key, http_client=client2), settings=settings
        )
    elif dep.provider == "cerebras":
        from pydantic_ai.models.cerebras import CerebrasModel
        from pydantic_ai.providers.cerebras import CerebrasProvider

        client2 = httpx2.AsyncClient(event_hooks=hooks, timeout=httpx2.Timeout(_TIMEOUT, connect=5.0))
        model = CerebrasModel(
            dep.model, provider=CerebrasProvider(api_key=api_key, http_client=client2), settings=settings
        )
    elif dep.provider == "openrouter":
        from pydantic_ai.models.openrouter import OpenRouterModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        client2 = httpx2.AsyncClient(event_hooks=hooks, timeout=httpx2.Timeout(_TIMEOUT, connect=5.0))
        model = OpenRouterModel(
            dep.model,
            provider=OpenRouterProvider(api_key=api_key, app_title="AIVA", http_client=client2),
            settings=settings,
        )
    elif dep.provider == "openai_compatible":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if not dep.base_url:
            raise ValueError(f"{dep.id}: openai_compatible deployments need base_url")
        client2 = httpx2.AsyncClient(event_hooks=hooks, timeout=httpx2.Timeout(_TIMEOUT, connect=5.0))
        model = OpenAIChatModel(
            dep.model,
            provider=OpenAIProvider(base_url=dep.base_url, api_key=api_key, http_client=client2),
            settings=settings,
        )
    else:  # pragma: no cover - guarded by the config Literal
        raise ValueError(f"unknown provider {dep.provider}")
    return GuardedModel(model, dep, quota)
