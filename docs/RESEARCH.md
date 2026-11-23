# Research notes (November 2026)

What was investigated before building AIVA, what was chosen, and why. Free tiers change
often — the router reads live rate-limit headers and `aiva doctor` validates keys and model
ids, so stale numbers here can't silently break a demo.

## 1. Free LLM APIs

| Provider | Free tier (as researched) | Speed | Notes | Role in AIVA |
|---|---|---|---|---|
| **Groq** | Per model: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` → 30 RPM, 1K req/day, 8K tokens/min, 200K tokens/day. Cached tokens don't count. Whisper: 20 RPM, 2K req/day, 7.2K audio-s/hour. | Fastest (LPU, 450–1000 tok/s) | Llama 3.x moved to Enterprise-only. Rate-limit headers on every response. | **Primary** LLM (3 models = 3 separate quotas) + **STT** |
| **Mistral** (Experiment plan) | 1 req/s, 500K tokens/min, very large monthly budget (third-party sources: ~1B/month) | Medium | Phone verification; free-tier data may be used for training. Voxtral STT supports Hindi. | **Main backup** (huge token budget) + STT fallback |
| **Google Gemini** | Flash-Lite ≈ 10 RPM / 500 req/day; Flash ≈ 5 RPM / 20 req/day (developer reports; Google shows exact limits only in AI Studio) | Medium | Free-tier data may be used to improve products. No rate-limit headers. | Backup |
| **Cerebras** | No permanent free tier any more: $5 trial credit (30 days) after adding a card; `qwen-3.8-27b` 300 RPM / 150K TPM on the trial | Very fast | | Optional |
| **OpenRouter** `:free` | 20 RPM, 50 req/day (1000/day after $10 lifetime top-up) | Varies | | Emergency fallback |
| GitHub Models | Reported retired in 2026 | — | | Not used |

**Decision:** no single free tier survives a 20-minute live demo with tool calls, so AIVA
pools several and routes by live quota (see ARCHITECTURE.md §3). With Groq + Mistral +
Gemini keys AIVA has roughly 3,500 requests/day of free capacity, and the token-hungry
part rides on Mistral's large budget once Groq's per-minute token window is busy.

Sources:
[Groq rate limits](https://console.groq.com/docs/rate-limits) ·
[Groq models](https://console.groq.com/docs/models) ·
[Cerebras rate limits](https://inference-docs.cerebras.ai/support/rate-limits) ·
[Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) ·
[Mistral free tier (help center)](https://help.mistral.ai/en/articles/225174-what-are-the-limits-of-the-free-tier) ·
[OpenRouter limits](https://openrouter.ai/docs/api-reference/limits) ·
[GitHub Models docs](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)

## 2. Speech

| Need | Options considered | Choice |
|---|---|---|
| STT | Groq Whisper (free), Mistral Voxtral (free tier, Hindi), Deepgram/AssemblyAI (credits), local mlx-whisper (RAM on an 8 GB Mac) | **Groq whisper-large-v3-turbo → Mistral Voxtral** |
| TTS | edge-tts (free Microsoft neural voices, `hi-IN-SwaraNeural`, `en-IN-NeerjaExpressiveNeural`), Groq Orpheus (English/Arabic only, 100 req/day), Kokoro (local), Piper (local), macOS `say` | **edge-tts** streaming, **`say`** offline fallback |
| VAD | Silero VAD v6 (MIT), WebRTC VAD, energy threshold | **Silero (ONNX, no torch)** — 2 MB model shipped in the repo |
| Wake word | openWakeWord, Porcupine, firmware-side ESP-SR | Not on the laptop (push-to-talk / hands-free); the xiaozhi firmware does wake word on-device in phase 2 |

Hinglish trick: Hindi voices read Devanagari well but garble romanised Hindi, so the
persona tells the model to write Hindi words in Devanagari and English words in English
("आज का weather बहुत अच्छा है"). Whisper gets a Devanagari+English style prompt so its
transcripts follow the same convention.

## 3. Open-source building blocks evaluated

| Project | Stars / licence | Verdict |
|---|---|---|
| [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) | ~34k, MIT | **Use (phase 2 firmware)**. Has our exact board; its protocol is our device protocol. |
| [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) | ~11k, MIT | Studied for protocol details; not used as a base (Java + Vue + MySQL stack, China-centric providers, heavy for an 8 GB Mac). |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) | ~17k, BSD-2 | Considered for the voice loop. Rejected: our needs are narrow (one protocol, one STT, one TTS) and quota-aware routing + xiaozhi framing are custom anyway; a lean session (~400 lines) is easier to reason about and to present. |
| [livekit/agents](https://github.com/livekit/agents) | ~15k, Apache-2.0 | Needs a LiveKit server; overkill here. |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | ~21k, MIT | **Use (brain)**. v2 brings `SelectModel`, `ModelFallback`, `PrepareTools`, `ProcessHistory`, MCP toolsets and streaming events — exactly the primitives needed. |
| [playfultechnology/esp32-eyes](https://github.com/playfultechnology/esp32-eyes) | AGPL-3.0 | **Use (face)**: eye presets + drawing algorithm ported to TypeScript; the same C++ library can draw them on the OLED. |
| [FluxGarage/RoboEyes](https://github.com/FluxGarage/RoboEyes) | ~1k, GPL-3.0 | Nice eyes, fewer moods, no mouth; esp32-eyes preferred. |
| [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | ~11k, MIT | **Use**. |
| [rany2/edge-tts](https://github.com/rany2/edge-tts) | ~13k, LGPL/GPL | **Use**. |
| [deedy5/ddgs](https://github.com/deedy5/ddgs) | MIT | **Use** for search/news/videos (no key). |
| [pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 | **Use** for every PDF skill (HTML→PDF with Devanagari shaping). |
| [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | ~40k, Apache-2.0 | **Offered as a one-click MCP preset** for browser automation. |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | ~120k, MIT | Impressive but token-hungry (sends page state every step) — a poor fit for free tiers; Playwright MCP is opt-in instead. |

Licensing: the repo is AGPL-3.0-or-later, which is compatible with every component above
(MIT/BSD/Apache-2.0/LGPL/GPL/AGPL). Fine for this non-commercial project.

## 4. Hardware findings

* **KY-038 is not a voice microphone** — it's an electret capsule + LM393 comparator meant
  for clap/loudness detection. Its analog output is noisy and low-fidelity; speech-to-text
  quality would be poor. The firmware expects an **INMP441 I²S MEMS mic**.
* **MAX98357A vs a 0.25 W speaker** — the amp can push ~1.8 W into 8 Ω at 5 V. Set the
  lowest gain (GAIN → VDD through 100 kΩ = 3 dB) and cap volume in firmware.
* The xiaozhi `bread-compact-wifi` pin map (mic WS/SCK/SD = GPIO 4/5/6, amp DIN/BCLK/LRC =
  GPIO 7/15/16, OLED SDA/SCL = GPIO 41/42) is reproduced in [HARDWARE.md](HARDWARE.md).
