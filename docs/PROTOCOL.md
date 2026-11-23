# Device protocol

AIVA's server implements the [xiaozhi-esp32 WebSocket protocol](https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md)
so the unmodified firmware can be its body, plus a few **AIVA extensions** used by the
browser simulator (only sent to devices that announce `features.aiva = true`).

## Endpoints

| Endpoint | Purpose |
|---|---|
| `WS  /xiaozhi/v1/` | Voice session. Headers `Authorization: Bearer <token>`, `Device-Id`, `Client-Id`, `Protocol-Version` (browsers may pass `?device-id=&client-id=&token=` instead). |
| `GET/POST /xiaozhi/ota/` | Firmware check-in. Returns `websocket.url` (this Mac's LAN IP) and `websocket.token`, plus server time. |

If `server.device_token` is set in the config, devices must present it.

## Handshake

Device → server (first text frame, within 10 s):

```json
{"type": "hello", "version": 1, "transport": "websocket",
 "features": {"mcp": true, "aec": true, "aiva": true},
 "audio_params": {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60}}
```

Server → device:

```json
{"type": "hello", "transport": "websocket", "session_id": "3f9c1a2b7d4e",
 "audio_params": {"format": "opus", "sample_rate": 24000, "channels": 1, "frame_duration": 60}}
```

`format` is `opus` (ESP32) or `pcm16` (AIVA extension: raw little-endian 16-bit mono —
the simulator sends 16 kHz / 20 ms frames). The server always sends 24 kHz audio in 60 ms
frames, in the device's format.

## Device → server

| Message | Meaning |
|---|---|
| binary frame | Microphone audio (while listening; also while speaking if the device has AEC → barge-in) |
| `{"type":"listen","state":"start","mode":"auto"}` | Hands-free: server-side VAD finds each utterance; keeps listening after replies |
| `{"type":"listen","state":"start","mode":"manual"}` | Push-to-talk: audio until `stop` is one utterance |
| `{"type":"listen","state":"stop"}` | Stop listening (processes a manual utterance) |
| `{"type":"listen","state":"detect","text":"Hi AIVA"}` | Wake word fired on the device (≤ 3 words → quick "जी?"; longer text is treated as a command) |
| `{"type":"abort","reason":"…"}` | Stop speaking now |
| `{"type":"chat","text":"…"}` | *AIVA ext.* typed input |
| `{"type":"mcp","payload":{…}}` | Device-side MCP (JSON-RPC) — logged, reserved for phase 2 |

## Server → device

| Message | Meaning |
|---|---|
| `{"type":"stt","text":"…"}` | What the user said |
| `{"type":"llm","emotion":"happy","text":"😊"}` | Show an emotion (one of the 21 xiaozhi emotions) — sent in sentence order |
| `{"type":"tts","state":"start"}` | Speaking begins (device → speaking state) |
| `{"type":"tts","state":"sentence_start","text":"…"}` | Caption for the sentence now playing |
| binary frames | TTS audio, paced at real time + ~350 ms lead |
| `{"type":"tts","state":"stop"}` | Speaking finished (or interrupted) |
| `{"type":"alert","status":"Error","message":"…","emotion":"sad"}` | Fatal problem (e.g. Opus unavailable) |
| `{"type":"aiva","kind":"state","state":"listening"}` | *ext.* idle / listening / thinking / speaking |
| `{"type":"aiva","kind":"vad","speaking":true}` | *ext.* the user started/stopped talking |
| `{"type":"aiva","kind":"tool","name":"web_search","status":"start"}` | *ext.* tool activity for captions |
| `{"type":"aiva","kind":"notice","text":"…","level":"warning"}` | *ext.* spoken system notice (e.g. quota low) |
| `{"type":"aiva","kind":"face","animation":"dance"}` | *ext.* play a face animation |
| `{"type":"aiva","kind":"flush"}` | *ext.* drop any buffered audio immediately (barge-in) |

## Emotions

`neutral happy laughing funny sad angry crying loving embarrassed surprised shocked
thinking winking cool relaxed delicious kissy confident sleepy silly confused`

## Animations (AIVA extension)

`dance wink blink look_around nod shake_head laugh love sleep wake_up dizzy`
