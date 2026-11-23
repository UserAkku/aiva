"""Layered configuration.

Precedence (low → high):
    1. defaults in the pydantic models below
    2. ``config/aiva.yaml``            (tracked in git, clean defaults)
    3. ``data/overrides.yaml``         (written by the dashboard, git-ignored)
Secrets never live in YAML: they come from the environment / ``.env``.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["groq", "mistral", "google", "cerebras", "openrouter", "openai_compatible"]


def project_root() -> Path:
    """Repo root: ``$AIVA_HOME`` if set, else the first parent that has ``config/aiva.yaml``."""
    if env := os.environ.get("AIVA_HOME"):
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in [Path.cwd(), *here.parents]:
        if (parent / "config" / "aiva.yaml").exists():
            return parent
    return Path.cwd()


# ── config models ────────────────────────────────────────────────────────────


class Limits(BaseModel):
    """Free-tier limits of one deployment. ``None`` = unknown / not enforced."""

    rpm: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None


class DeploymentConfig(BaseModel):
    id: str
    provider: ProviderName
    model: str
    priority: int = 50
    enabled: bool = True
    limits: Limits = Field(default_factory=Limits)
    settings: dict[str, Any] = Field(default_factory=dict)
    base_url: str | None = None  # only for provider=openai_compatible
    api_key_env: str | None = None  # only for provider=openai_compatible


class LLMConfig(BaseModel):
    max_output_tokens: int = 450
    temperature: float = 0.7
    history_turns: int = 6
    first_token_timeout_s: float = 6.0
    warn_at: list[float] = Field(default_factory=lambda: [0.25, 0.10])
    deployments: list[DeploymentConfig] = Field(default_factory=list)


class AssistantConfig(BaseModel):
    name: str = "AIVA"
    owner_name: str = ""
    language: Literal["hinglish", "english", "hindi"] = "hinglish"
    city: str = ""
    personality: str = "playful, warm and witty desk robot"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    device_token: str = ""
    open_browser: bool = True


class STTConfig(BaseModel):
    provider: Literal["groq"] = "groq"
    model: str = "whisper-large-v3-turbo"
    language: str = ""
    prompt: str = ""


class TTSConfig(BaseModel):
    engine: Literal["edge", "say"] = "edge"
    voice_hindi: str = "hi-IN-SwaraNeural"
    voice_english: str = "en-IN-NeerjaExpressiveNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    say_voice_hindi: str = "Lekha"
    say_voice_english: str = "Tara"


class VoiceConfig(BaseModel):
    vad_threshold: float = 0.55
    min_speech_ms: int = 250
    end_silence_ms: int = 650
    max_utterance_s: float = 25.0
    pre_roll_ms: int = 300
    barge_in: bool = True
    playback_lead_ms: int = 350


class ToolsConfig(BaseModel):
    disabled: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    workspace: str = "~/Documents/AIVA"
    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        path = Path(self.workspace).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path


# ── secrets ──────────────────────────────────────────────────────────────────

#: provider -> env var holding its key (first match wins)
PROVIDER_KEY_ENV: dict[str, tuple[str, ...]] = {
    "groq": ("GROQ_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "cerebras": ("CEREBRAS_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
}


class Secrets(BaseSettings):
    """API keys from the process env or ``.env``. Re-created after the dashboard edits ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: SecretStr | None = None
    mistral_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    cerebras_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None

    def key_for(self, provider: str, env_name: str | None = None) -> str | None:
        names = (env_name,) if env_name else PROVIDER_KEY_ENV.get(provider, ())
        for name in names:
            if not name:
                continue
            value = getattr(self, name.lower(), None)
            if isinstance(value, SecretStr) and value.get_secret_value().strip():
                return value.get_secret_value().strip()
            if raw := os.environ.get(name, "").strip():
                return raw
        return None


# ── loading / saving ─────────────────────────────────────────────────────────


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``patch`` into a copy of ``base`` (lists are replaced, not merged)."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class ConfigStore:
    """Owns config files: loads the merged config and persists dashboard overrides."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.base_path = self.root / "config" / "aiva.yaml"
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.overrides_path = self.data_dir / "overrides.yaml"
        self.env_path = self.root / ".env"

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def load(self) -> AppConfig:
        merged = deep_merge(self._read_yaml(self.base_path), self._read_yaml(self.overrides_path))
        return AppConfig.model_validate(merged)

    def overrides(self) -> dict[str, Any]:
        return self._read_yaml(self.overrides_path)

    def save_overrides(self, patch: dict[str, Any]) -> AppConfig:
        """Merge ``patch`` into the overrides file, validate, and return the new config."""
        new_overrides = deep_merge(self.overrides(), patch)
        merged = deep_merge(self._read_yaml(self.base_path), new_overrides)
        config = AppConfig.model_validate(merged)  # raises before anything is written
        self.overrides_path.write_text(yaml.safe_dump(new_overrides, allow_unicode=True, sort_keys=False))
        return config

    def load_secrets(self) -> Secrets:
        return Secrets(_env_file=self.env_path)  # type: ignore[call-arg]

    def set_secret(self, name: str, value: str) -> None:
        """Insert or replace ``NAME=value`` in ``.env`` (created with 0600 permissions)."""
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError(f"invalid env var name: {name!r}")
        if "\n" in value or "\r" in value:
            raise ValueError("secret values must be a single line")
        lines = self.env_path.read_text(encoding="utf-8").splitlines() if self.env_path.exists() else []
        entry = f"{name}={value}"
        for i, line in enumerate(lines):
            if line.split("=", 1)[0].strip() == name:
                lines[i] = entry
                break
        else:
            lines.append(entry)
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.env_path.chmod(0o600)
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
