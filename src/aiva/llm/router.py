"""Quota-aware LLM router built on pydantic-ai capabilities.

* ``SelectModel``  — before every request step, pick the deployment with the best
  quota score (healthy, not cooling down, enough tokens left, lowest priority).
* ``ModelFallback`` — if that request still fails (429, 5xx, timeout, no first
  token in time), immediately retry the step on the next deployment. Exhausted
  deployments raise :class:`QuotaSkip` without touching the network, so walking
  the chain costs microseconds.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic_ai.capabilities import ModelFallback, SelectModel
from pydantic_ai.exceptions import ContentFilterError, ModelAPIError
from pydantic_ai.models import Model

from ..config import AppConfig, Secrets
from .models import GuardedModel, build_model, estimate_request_tokens
from .quota import QuotaGuard


class LLMRouter:
    def __init__(self, config: AppConfig, secrets: Secrets, quota: QuotaGuard) -> None:
        self.quota = quota
        self.models: dict[str, GuardedModel] = {}
        self.build_errors: dict[str, str] = {}
        self.reconfigure(config, secrets)

    def reconfigure(self, config: AppConfig, secrets: Secrets) -> None:
        """(Re)build every deployment — called at start-up and when keys/config change."""
        self.config = config
        self.models.clear()
        self.build_errors.clear()
        for dep in sorted(config.llm.deployments, key=lambda d: d.priority):
            has_key = bool(secrets.key_for(dep.provider, dep.api_key_env)) and dep.enabled
            self.quota.register(dep, has_key)
            if not has_key:
                continue
            try:
                self.models[dep.id] = build_model(dep, config.llm, secrets, self.quota)
            except Exception as exc:  # a broken optional provider must never take AIVA down
                self.build_errors[dep.id] = str(exc)
                logger.error("could not build LLM deployment {}: {}", dep.id, exc)
        logger.info(
            "LLM router ready with {} deployment(s): {}",
            len(self.models),
            ", ".join(self.models) or "none (add an API key in the dashboard)",
        )

    @property
    def available(self) -> bool:
        return bool(self.models)

    def chain(self) -> list[GuardedModel]:
        return sorted(self.models.values(), key=lambda m: m.deployment.priority)

    def ranked(self, est_tokens: int) -> list[GuardedModel]:
        scored = [(self.quota.score(m.deployment_id, est_tokens), m) for m in self.chain()]
        usable = [(s, m) for s, m in scored if s != float("-inf")]
        usable.sort(key=lambda sm: sm[0], reverse=True)
        return [m for _, m in usable]

    def select(self, ctx: Any) -> Model:
        """``SelectModel`` hook: best-scoring deployment for this request step."""
        estimate = estimate_request_tokens(list(ctx.messages)) + 1500  # + instructions & tool schemas
        ranked = self.ranked(estimate)
        choice = ranked[0] if ranked else self.chain()[0]
        logger.debug("router → {} (est. {} tokens)", choice.deployment_id, estimate)
        return choice

    def capabilities(self) -> list[Any]:
        if not self.models:
            return []
        return [
            SelectModel(self.select),
            ModelFallback(*self.chain(), fallback_on=(ModelAPIError, ContentFilterError, TimeoutError)),
        ]

    def deployment_for(self, model_name: str | None) -> str | None:
        for dep_id, model in self.models.items():
            if model.model_name == model_name:
                return dep_id
        return None
