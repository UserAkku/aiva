"""The router must fail over instantly and skip exhausted deployments without a network call."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from aiva.config import DeploymentConfig, Limits
from aiva.events import EventBus
from aiva.llm.models import GuardedModel
from aiva.llm.quota import QuotaGuard
from aiva.llm.router import LLMRouter
from aiva.storage import Database


class FakeRouter(LLMRouter):
    """LLMRouter with injected models instead of real providers."""

    def __init__(self, quota: QuotaGuard, models: list[GuardedModel]) -> None:
        self.quota = quota
        self.models = {m.deployment_id: m for m in models}
        self.build_errors = {}


def make_guarded(
    quota: QuotaGuard, dep_id: str, priority: int, fn, limits: Limits | None = None
) -> GuardedModel:
    dep = DeploymentConfig(
        id=dep_id, provider="groq", model=dep_id, priority=priority, limits=limits or Limits()
    )
    quota.register(dep, has_key=True)
    return GuardedModel(FunctionModel(fn, model_name=dep_id), dep, quota)


@pytest.fixture
def quota(tmp_path: Path) -> QuotaGuard:
    return QuotaGuard(Database(tmp_path / "t.db"), EventBus())


async def test_fallback_on_rate_limit_then_sticks_to_healthy(quota: QuotaGuard) -> None:
    calls: list[str] = []

    def rate_limited(messages: list[ModelMessage], info: AgentInfo):
        calls.append("primary")
        raise ModelHTTPError(429, "primary", body={"error": "rate limit"}, retry_after=30)

    def healthy(messages: list[ModelMessage], info: AgentInfo):
        from pydantic_ai.messages import ModelResponse, TextPart

        calls.append("backup")
        return ModelResponse(parts=[TextPart("<happy> backup here")])

    primary = make_guarded(quota, "primary", 10, rate_limited)
    backup = make_guarded(quota, "backup", 20, healthy)
    router = FakeRouter(quota, [primary, backup])
    agent = Agent(capabilities=router.capabilities())

    result = await agent.run("hi")
    assert "backup here" in result.output
    assert calls == ["primary", "backup"]
    assert quota.states["primary"].cooldown_until > 0

    # second run: primary is cooling down → skipped without being called
    calls.clear()
    result = await agent.run("hi again")
    assert calls == ["backup"]


async def test_exhausted_daily_quota_is_skipped(quota: QuotaGuard) -> None:
    calls: list[str] = []

    def answer(name: str):
        def fn(messages: list[ModelMessage], info: AgentInfo):
            from pydantic_ai.messages import ModelResponse, TextPart

            calls.append(name)
            return ModelResponse(parts=[TextPart(f"from {name}")])

        return fn

    primary = make_guarded(quota, "primary", 10, answer("primary"), Limits(rpd=2))
    backup = make_guarded(quota, "backup", 20, answer("backup"))
    agent = Agent(capabilities=FakeRouter(quota, [primary, backup]).capabilities())

    for _ in range(2):
        assert (await agent.run("x")).output == "from primary"
    assert (await agent.run("x")).output == "from backup"  # primary used its 2 requests/day
    assert calls == ["primary", "primary", "backup"]


def test_header_parsing_groq_style(quota: QuotaGuard) -> None:
    dep = DeploymentConfig(id="g", provider="groq", model="m", limits=Limits(rpd=1000, tpm=8000))
    quota.register(dep, has_key=True)
    quota.on_headers(
        "g",
        200,
        {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "40",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "7000",
            "x-ratelimit-reset-requests": "2h1m3.5s",
            "x-ratelimit-reset-tokens": "7.66s",
        },
    )
    state = quota.states["g"]
    assert state.remaining("rpd", __import__("time").time()) == (40, 1000)
    assert state.daily_fraction(__import__("time").time()) == pytest.approx(0.04)
    ok, reason = quota.fits("g", 7500)
    assert not ok and "tpm" in reason


def test_warnings_fire_once(quota: QuotaGuard) -> None:
    for i, name in enumerate(("a", "b")):
        quota.register(
            DeploymentConfig(id=name, provider="groq", model=name, priority=i, limits=Limits(rpd=10)),
            has_key=True,
        )
    for _ in range(8):
        quota.on_success("a", 10, 10, 100)
        quota.on_success("b", 10, 10, 100)
    warnings = quota.pop_warnings()
    keys = {w.key for w in warnings}
    assert "primary-25" in keys and "pool-25" in keys
    for _ in range(1):
        quota.on_success("a", 10, 10, 100)
    assert all(w.key not in keys for w in quota.pop_warnings())


def test_auth_cooldown_cleared_when_reconfigured(quota: QuotaGuard) -> None:
    dep = DeploymentConfig(id="g", provider="groq", model="m")
    quota.register(dep, has_key=True)
    quota.on_failure("g", "auth", "401 invalid key")
    assert not quota.fits("g", 10)[0]
    quota.register(dep, has_key=True)  # key fixed on the dashboard → services.reload()
    assert quota.fits("g", 10)[0]
    quota.on_failure("g", "rate_limit", "429", retry_after=30)
    quota.register(dep, has_key=True)
    assert not quota.fits("g", 10)[0]  # real rate limits are NOT forgiven by a reload


def test_all_auth_errors_detection() -> None:
    from pydantic_ai.exceptions import ModelHTTPError

    from aiva.brain.agent import _all_auth_errors

    auth = [ModelHTTPError(401, "a"), ModelHTTPError(403, "b")]
    assert _all_auth_errors(ExceptionGroup("all failed", auth))
    assert not _all_auth_errors(ExceptionGroup("mixed", [*auth, ModelHTTPError(429, "c")]))
