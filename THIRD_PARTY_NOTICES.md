# Third-party notices

AIVA is assembled from open-source projects. Thank you to all of them.

## Incorporated code / data

| Project | Licence | Used for |
|---|---|---|
| [zayfod/pycozmo](https://github.com/zayfod/pycozmo) — `ProceduralFace` | MIT | Cozmo-style procedural eyes (43 parameters, eyelids), ported to TypeScript in `web/src/face/procedural.ts` |
| "Expressive Eyes" by Catherine Chambers (via pycozmo) | MIT (as distributed in pycozmo) | The 25 eye expressions AIVA's 21 emotions are built on |
| [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | MIT | `src/aiva/assets/silero_vad.onnx` voice-activity model |
| [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) | MIT | WebSocket protocol, emotion vocabulary and board pin map (firmware for phase 2) |

## Runtime dependencies (installed, not vendored)

| Project | Licence |
|---|---|
| pydantic-ai, pydantic, pydantic-settings | MIT |
| FastAPI, Starlette, Uvicorn | MIT / BSD-3 |
| onnxruntime | MIT |
| numpy, soxr | BSD / LGPL-2.1 |
| miniaudio (pyminiaudio) | MIT |
| edge-tts | LGPL-3.0 / GPL-3.0 |
| PyMuPDF | AGPL-3.0 |
| ddgs | MIT |
| trafilatura | Apache-2.0 |
| simpleeval | MIT |
| httpx, loguru, typer, rich, PyYAML | BSD / MIT |
| React, Vite, Tailwind CSS, lucide-react, clsx | MIT / ISC |

## Services (free tiers, your own keys)

Groq, Mistral AI, Google Gemini, Cerebras, OpenRouter (LLMs); Groq Whisper and Mistral
Voxtral (speech-to-text); Sarvam AI Bulbul and Microsoft Edge read-aloud voices via edge-tts
(text-to-speech);
Open-Meteo (weather), Frankfurter/ECB (exchange rates), Wikipedia, DuckDuckGo.
Use them within their terms of service.
