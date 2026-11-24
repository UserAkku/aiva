"""QuotaGuard — knows how much free quota every deployment has left.

Two sources of truth are combined:

* **Rate-limit headers** returned by the provider on every response (Groq, Cerebras,
  Mistral…). These are exact, so they win whenever they are fresh.
* **Local accounting** (sliding windows + a day counter persisted in SQLite) for
  providers that send no headers (Gemini) and for the time before the first call.

The router asks :meth:`QuotaGuard.fits` / :meth:`QuotaGuard.score` before every
request, so an exhausted deployment is skipped *before* it can fail, and
:meth:`QuotaGuard.pop_warnings` turns threshold crossings into sentences AIVA speaks
("my free limit is almost over…") so a live demo never hits a silent wall.
"""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from loguru import logger

from ..config import DeploymentConfig, Limits
from ..events import EventBus
from ..storage import Database
from .catalog import PROVIDERS

FailureKind = Literal["rate_limit", "auth", "server", "timeout", "bad_request", "other"]

_HEADER_FRESH_S = {"minute": 60.0, "hour": 3600.0, "day": 6 * 3600.0, "month": 24 * 3600.0}


def parse_duration(value: str) -> float | None:
    """'2m59.56s' / '7.66s' / '1h2m' / '120' / '350ms' → seconds."""
    text = value.strip().lower()
    try:
        return float(text)
    except ValueError:
        pass
    parts = re.findall(r"([\d.]+)\s*(ms|h|m|s)", text)
    if not parts:
        return None
    scale = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(num) * scale[unit] for num, unit in parts)


def parse_reset(value: str, now: float) -> float | None:
    """Reset headers come as durations ('7.66s'), seconds, or epoch timestamps (s or ms)."""
    seconds = parse_duration(value)
    if seconds is None:
        return None
    if seconds > 1e12:  # epoch milliseconds
        return seconds / 1000.0
    if seconds > 1e9:  # epoch seconds
        return seconds
    return now + seconds


@dataclass(slots=True)
class Bucket:
    limit: int | None = None
    remaining: int | None = None
    reset_at: float | None = None
    observed_at: float = 0.0


def parse_rate_limit_headers(
    provider: str, headers: Mapping[str, str], now: float | None = None
) -> tuple[dict[tuple[str, str], Bucket], float | None]:
    """Parse any ``*ratelimit*`` headers into ``{(kind, window): Bucket}`` plus ``retry-after``.

    Header names vary by provider (``x-ratelimit-remaining-requests`` on Groq means
    *per day*, ``x-ratelimit-remaining-tokens-minute`` on Cerebras, ...), so this is a
    tolerant name-based parser rather than a per-provider table.
    """
    now = time.time() if now is None else now
    info = PROVIDERS.get(provider)
    default_window = {
        "requests": info.header_request_window if info else "day",
        "tokens": info.header_token_window if info else "minute",
    }
    buckets: dict[tuple[str, str], Bucket] = {}
    retry_after: float | None = None
    for raw_name, value in headers.items():
        name = raw_name.lower()
        if name == "retry-after":
            retry_after = parse_duration(value)
            continue
        if "ratelimit" not in name:
            continue
        if "remaining" in name:
            attr = "remaining"
        elif "reset" in name:
            attr = "reset"
        elif "limit" in name.replace("ratelimit", ""):
            attr = "limit"
        else:
            continue
        if "request" in name or "-req-" in name or name.endswith("-req"):
            kind = "requests"
        elif "token" in name or "size" in name:
            kind = "tokens"
        else:
            continue
        window = next((w for w in ("minute", "hour", "day", "month") if w in name), default_window[kind])
        bucket = buckets.setdefault((kind, window), Bucket(observed_at=now))
        if attr == "reset":
            bucket.reset_at = parse_reset(value, now)
        else:
            try:
                setattr(bucket, attr, int(float(value)))
            except ValueError:
                continue
    return buckets, retry_after


@dataclass
class DeploymentState:
    id: str
    provider: str
    model: str
    priority: int
    limits: Limits
    has_key: bool = False
    buckets: dict[tuple[str, str], Bucket] = field(default_factory=dict)
    minute_requests: deque[float] = field(default_factory=deque)
    minute_tokens: deque[tuple[float, int]] = field(default_factory=deque)
    day_requests: deque[float] = field(default_factory=deque)
    day_tokens: deque[tuple[float, int]] = field(default_factory=deque)
    seeded_day_requests: int = 0
    seeded_day_tokens: int = 0
    cooldown_until: float = 0.0
    cooldown_reason: str = ""
    consecutive_failures: int = 0
    total_requests: int = 0
    total_errors: int = 0
    last_error: str | None = None
    last_ok_at: float | None = None
    last_request_at: float = 0.0
    last_latency_ms: float | None = None

    # ── sliding windows ──────────────────────────────────────────────────────
    def prune(self, now: float) -> None:
        while self.minute_requests and now - self.minute_requests[0] > 60:
            self.minute_requests.popleft()
        while self.minute_tokens and now - self.minute_tokens[0][0] > 60:
            self.minute_tokens.popleft()
        while self.day_requests and now - self.day_requests[0] > 86400:
            self.day_requests.popleft()
        while self.day_tokens and now - self.day_tokens[0][0] > 86400:
            self.day_tokens.popleft()

    def used(self, now: float) -> dict[str, int]:
        self.prune(now)
        return {
            "rpm": len(self.minute_requests),
            "tpm": sum(t for _, t in self.minute_tokens),
            "rpd": len(self.day_requests) + self.seeded_day_requests,
            "tpd": sum(t for _, t in self.day_tokens) + self.seeded_day_tokens,
        }

    def fresh_bucket(self, kind: str, window: str, now: float) -> Bucket | None:
        bucket = self.buckets.get((kind, window))
        if bucket is None or bucket.remaining is None:
            return None
        if bucket.reset_at is not None and now >= bucket.reset_at:
            return None  # the window has replenished since we saw it
        if now - bucket.observed_at > _HEADER_FRESH_S[window]:
            return None
        return bucket

    def remaining(self, metric: str, now: float) -> tuple[int | None, int | None]:
        """(remaining, limit) for ``rpm|tpm|rpd|tpd``; headers first, local accounting second."""
        kind, window = {
            "rpm": ("requests", "minute"),
            "tpm": ("tokens", "minute"),
            "rpd": ("requests", "day"),
            "tpd": ("tokens", "day"),
        }[metric]
        bucket = self.fresh_bucket(kind, window, now)
        if bucket is not None:
            return bucket.remaining, bucket.limit or getattr(self.limits, metric)
        limit = getattr(self.limits, metric)
        if limit is None:
            return None, None
        return max(limit - self.used(now)[metric], 0), limit

    def daily_fraction(self, now: float) -> float | None:
        """Share of the daily quota still available (min over requests and tokens)."""
        fractions = []
        for metric in ("rpd", "tpd"):
            remaining, limit = self.remaining(metric, now)
            if remaining is not None and limit:
                fractions.append(max(0.0, min(1.0, remaining / limit)))
        return min(fractions) if fractions else None


@dataclass(slots=True)
class Warning_:
    key: str
    level: Literal["info", "warning", "critical"]
    text_en: str
    text_hi: str


class QuotaGuard:
    def __init__(self, db: Database, bus: EventBus, warn_at: list[float] | None = None) -> None:
        self.db = db
        self.bus = bus
        self.warn_at = sorted(warn_at or [0.25, 0.10], reverse=True)
        self.states: dict[str, DeploymentState] = {}
        self._fired: set[str] = set()
        self._fired_day = self._today()
        self._pending: list[Warning_] = []
        self._provider_last_request: dict[str, float] = {}

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    # ── registration ─────────────────────────────────────────────────────────
    def register(self, dep: DeploymentConfig, has_key: bool) -> DeploymentState:
        state = self.states.get(dep.id)
        if state is None:
            state = DeploymentState(dep.id, dep.provider, dep.model, dep.priority, dep.limits)
            usage = self.db.usage_for_day(self._today()).get(dep.id)
            if usage:  # survive restarts: seed today's local counters from the database
                state.seeded_day_requests = int(usage["requests"])
                state.seeded_day_tokens = int(usage["input_tokens"]) + int(usage["output_tokens"])
            self.states[dep.id] = state
        state.provider, state.model, state.priority, state.limits = (
            dep.provider,
            dep.model,
            dep.priority,
            dep.limits,
        )
        state.has_key = has_key
        if state.cooldown_reason.startswith(("auth", "bad_request")):
            # the key or model id may have just been fixed in the dashboard: try again right away
            state.cooldown_until, state.cooldown_reason = 0.0, ""
            state.consecutive_failures = 0
        return state

    def active(self) -> list[DeploymentState]:
        return [s for s in self.states.values() if s.has_key]

    # ── observations ─────────────────────────────────────────────────────────
    def on_headers(self, dep_id: str, status_code: int, headers: Mapping[str, str]) -> None:
        state = self.states.get(dep_id)
        if state is None:
            return
        now = time.time()
        buckets, retry_after = parse_rate_limit_headers(state.provider, headers, now)
        state.buckets.update(buckets)
        if status_code == 429 and any(b.limit == 0 for b in buckets.values()):
            self._cooldown(
                state, 1800.0, "provider limit is 0 for this model — not included in your free plan"
            )
            state.last_error = "this model isn't available on your free plan (limit 0)"
            return
        if status_code == 429:
            self._cooldown(
                state, retry_after or self._exhausted_reset(state, now) or 20.0, "rate limited (429)"
            )

    def on_success(self, dep_id: str, input_tokens: int, output_tokens: int, latency_ms: float) -> None:
        state = self.states.get(dep_id)
        if state is None:
            return
        now = time.time()
        tokens = max(0, input_tokens) + max(0, output_tokens)
        state.minute_requests.append(now)
        state.day_requests.append(now)
        state.minute_tokens.append((now, tokens))
        state.day_tokens.append((now, tokens))
        state.total_requests += 1
        state.consecutive_failures = 0
        state.last_ok_at = now
        state.last_latency_ms = latency_ms
        state.last_error = None
        self.db.add_usage(self._today(), dep_id, 1, input_tokens, output_tokens, 0)
        self._evaluate_warnings()

    def on_failure(
        self, dep_id: str, kind: FailureKind, message: str, retry_after: float | None = None
    ) -> None:
        state = self.states.get(dep_id)
        if state is None:
            return
        state.total_errors += 1
        state.consecutive_failures += 1
        state.last_error = f"{kind}: {message}"[:300]
        self.db.add_usage(self._today(), dep_id, 0, 0, 0, 1)
        if kind == "rate_limit":
            wait = retry_after or self._exhausted_reset(state, time.time()) or 20.0
        elif kind == "auth":
            wait = 3600.0  # bad key: don't hammer it; the dashboard shows the error
        elif kind == "bad_request":
            wait = 300.0  # e.g. model id retired — try again later
        else:
            wait = min(10.0 * 2 ** (state.consecutive_failures - 1), 300.0)
        self._cooldown(state, wait, state.last_error)
        logger.warning("LLM deployment {} failed ({}); cooling down {:.0f}s", dep_id, kind, wait)

    def _exhausted_reset(self, state: DeploymentState, now: float) -> float | None:
        for bucket in state.buckets.values():
            if bucket.remaining == 0 and bucket.reset_at and bucket.reset_at > now:
                return bucket.reset_at - now
        return None

    def _cooldown(self, state: DeploymentState, seconds: float, reason: str) -> None:
        until = time.time() + max(1.0, seconds)
        if until > state.cooldown_until:
            state.cooldown_until, state.cooldown_reason = until, reason
        self.bus.publish("quota.cooldown", deployment=state.id, seconds=round(seconds, 1), reason=reason)

    # ── decisions ────────────────────────────────────────────────────────────
    def pace_delay(self, dep_id: str) -> float:
        """Seconds to wait before the next request so a requests-per-second limit is respected.

        Per-second limits on free tiers are per account (Mistral: 1 req/s for the whole
        workspace), so pacing is shared by every deployment of the same provider.
        """
        state = self.states.get(dep_id)
        if state is None or not state.limits.rps:
            return 0.0
        last = self._provider_last_request.get(state.provider, 0.0)
        return max(0.0, last + 1.0 / state.limits.rps - time.monotonic())

    def mark_request(self, dep_id: str) -> None:
        if state := self.states.get(dep_id):
            now = time.monotonic()
            state.last_request_at = now
            self._provider_last_request[state.provider] = now

    def fits(self, dep_id: str, est_tokens: int) -> tuple[bool, str]:
        state = self.states.get(dep_id)
        if state is None or not state.has_key:
            return False, "no API key"
        now = time.time()
        if now < state.cooldown_until:
            return False, f"cooling down {state.cooldown_until - now:.0f}s ({state.cooldown_reason})"
        for metric, need in (("rpm", 1), ("rpd", 1), ("tpm", est_tokens), ("tpd", est_tokens)):
            remaining, _ = state.remaining(metric, now)
            if remaining is not None and remaining < need:
                return False, f"{metric} exhausted ({remaining} left, need ~{need})"
        return True, "ok"

    def score(self, dep_id: str, est_tokens: int) -> float:
        ok, _ = self.fits(dep_id, est_tokens)
        if not ok:
            return float("-inf")
        state = self.states[dep_id]
        score = 100.0 - state.priority
        fraction = state.daily_fraction(time.time())
        if fraction is not None:
            if fraction < 0.10:
                score -= 40
            elif fraction < 0.25:
                score -= 15
        score -= 12 * state.consecutive_failures
        return score

    def pool_fraction(self) -> float | None:
        """Capacity-weighted share of today's quota left across all keyed deployments."""
        now = time.time()
        total = left = 0.0
        for state in self.active():
            remaining, limit = state.remaining("rpd", now)
            if remaining is None or not limit:
                continue
            total += limit
            left += remaining
        return (left / total) if total else None

    # ── spoken warnings ──────────────────────────────────────────────────────
    def _evaluate_warnings(self) -> None:
        today = self._today()
        if today != self._fired_day:
            self._fired, self._fired_day = set(), today
        now = time.time()
        active = sorted(self.active(), key=lambda s: s.priority)
        if not active:
            return
        primary = active[0]
        primary_frac = primary.daily_fraction(now)
        pool = self.pool_fraction()
        for threshold in self.warn_at:
            pct = int(threshold * 100)
            if primary_frac is not None and primary_frac <= threshold and len(active) > 1:
                self._queue(
                    Warning_(
                        f"primary-{pct}",
                        "info",
                        f"Quick heads-up: only about {round(primary_frac * 100)} percent of my main "
                        f"{PROVIDERS[primary.provider].label} quota is left today, so I may switch to a backup brain.",
                        f"एक छोटी सी update: मेरी main {PROVIDERS[primary.provider].label} limit का सिर्फ "
                        f"{round(primary_frac * 100)} percent बचा है, ज़रूरत पड़ी तो मैं backup brain पे switch कर लूँगी।",
                    )
                )
            if pool is not None and pool <= threshold:
                critical = threshold <= min(self.warn_at)
                self._queue(
                    Warning_(
                        f"pool-{pct}",
                        "critical" if critical else "warning",
                        f"{'Alert' if critical else 'Heads-up'}! Only about {round(pool * 100)} percent of "
                        f"today's total free AI quota is left."
                        + (" I might stop answering soon." if critical else ""),
                        f"{'Alert' if critical else 'Heads-up'}! आज की total free limit का बस "
                        f"{round(pool * 100)} percent बचा है।"
                        + (" थोड़ी देर में मैं जवाब देना बंद कर सकती हूँ।" if critical else ""),
                    )
                )

    def _queue(self, warning: Warning_) -> None:
        if warning.key in self._fired:
            return
        self._fired.add(warning.key)
        self._pending.append(warning)
        self.bus.publish("quota.warning", key=warning.key, level=warning.level, text=warning.text_en)
        logger.warning("quota warning: {}", warning.text_en)

    def pop_warnings(self) -> list[Warning_]:
        pending, self._pending = self._pending, []
        return pending

    # ── reporting ────────────────────────────────────────────────────────────
    def snapshot(self) -> list[dict[str, Any]]:
        now = time.time()
        rows = []
        for state in sorted(self.states.values(), key=lambda s: s.priority):
            metrics = {}
            for metric in ("rpm", "rpd", "tpm", "tpd"):
                remaining, limit = state.remaining(metric, now)
                metrics[metric] = {"remaining": remaining, "limit": limit}
            rows.append(
                {
                    "id": state.id,
                    "provider": state.provider,
                    "model": state.model,
                    "priority": state.priority,
                    "has_key": state.has_key,
                    "metrics": metrics,
                    "daily_fraction": state.daily_fraction(now),
                    "cooldown_s": max(0.0, round(state.cooldown_until - now, 1)),
                    "cooldown_reason": state.cooldown_reason if state.cooldown_until > now else "",
                    "requests": state.total_requests,
                    "errors": state.total_errors,
                    "last_error": state.last_error,
                    "last_latency_ms": state.last_latency_ms,
                    "status": self._status(state, now),
                }
            )
        return rows

    def _status(self, state: DeploymentState, now: float) -> str:
        if not state.has_key:
            return "no-key"
        if now < state.cooldown_until:
            return "cooldown"
        fraction = state.daily_fraction(now)
        if fraction is not None and fraction < 0.10:
            return "low"
        return "ready"
