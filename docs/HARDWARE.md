# Hardware (phase 2): giving AIVA a body

The plan: flash the open-source [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)
firmware (board **bread-compact-wifi-128x64**) and point it at this Mac. The server already
speaks its protocol, so the only server-side work left is optional polish (drawing AIVA's
custom face on the OLED instead of xiaozhi's emoji glyphs).

## Bill of materials

| Part | Status | Notes |
|---|---|---|
| ESP32-S3 dev board (N16R8 recommended) | ✅ have | PSRAM helps the firmware |
| **INMP441 I²S MEMS microphone** | ❌ **buy** (≈ ₹150–250) | Replaces the KY-038 — see below |
| MAX98357A I²S amplifier | ✅ have | Set the lowest gain |
| 8 Ω 0.25 W coin speaker | ✅ have | Protect it: low gain + volume cap (≤ 60%) |
| 0.96″ SSD1306 128×64 I²C OLED | ✅ have | 1.3″ SH1106 also supported (menuconfig) |
| Push button (optional) | — | GPIO 0 (BOOT) already works as talk/wake |

### Why not the KY-038?
The KY-038 is a sound-*level* detector: an electret capsule plus an LM393 comparator with a
digital "loud/quiet" output and a crude analog output. Its signal is noisy, unfiltered and
not designed for speech — speech-to-text accuracy would be bad and the firmware has no
driver for it. The INMP441 is a 24-bit I²S digital microphone made for exactly this. (Keep the
KY-038 for a fun "clap to wake AIVA" trick on a spare GPIO if you like.)

### Protecting the 0.25 W speaker
MAX98357A can deliver ~1.8 W into 8 Ω at 5 V, enough to destroy a 0.25 W coin speaker. Wire
its **GAIN pin to VIN through a 100 kΩ resistor** (3 dB, the lowest setting; the default
floating pin is 9 dB) and keep the firmware volume ≤ 60%.

## Wiring (xiaozhi `bread-compact-wifi`)

| Module | Pin | ESP32-S3 |
|---|---|---|
| INMP441 | WS | GPIO 4 |
| INMP441 | SCK | GPIO 5 |
| INMP441 | SD | GPIO 6 |
| INMP441 | L/R | GND (left channel) |
| INMP441 | VDD / GND | 3V3 / GND |
| MAX98357A | DIN | GPIO 7 |
| MAX98357A | BCLK | GPIO 15 |
| MAX98357A | LRC | GPIO 16 |
| MAX98357A | VIN / GND | 5V / GND |
| SSD1306 | SDA | GPIO 41 |
| SSD1306 | SCL | GPIO 42 |
| SSD1306 | VCC / GND | 3V3 / GND |

(Source: `main/boards/bread-compact-wifi/config.h` in xiaozhi-esp32.)

## Flashing & connecting

1. Install ESP-IDF 5.4+ (`brew install cmake ninja dfu-util` + the ESP-IDF installer).
2. `git clone https://github.com/78/xiaozhi-esp32 firmware/xiaozhi-esp32` (kept out of git; or add it as a submodule).
3. `idf.py set-target esp32s3`, then `idf.py menuconfig` (menu names can differ slightly between firmware versions):
   * *Xiaozhi Assistant → Board Type* → **Bread Compact WiFi** and OLED **SSD1306 128×64**.
   * *Xiaozhi Assistant → Default OTA URL* → the **OTA URL shown on AIVA's Hardware page**,
     e.g. `http://192.168.1.23:8000/xiaozhi/ota/` (Mac and ESP32 on the same Wi-Fi).
4. `idf.py build flash monitor`. On first boot, join the `Xiaozhi-xxxx` hotspot from your
   phone and enter your Wi-Fi details.
5. The device checks in at `/xiaozhi/ota/`, receives `ws://<mac-ip>:8000/xiaozhi/v1/`,
   and appears on the dashboard's Hardware page. Press BOOT (or say the wake word) and talk.
6. On the Mac: `brew install opus && uv sync --extra hardware` (Opus codec for the ESP32's audio).

## Phase 2b: AIVA's face on the real OLED

xiaozhi's OLED UI shows an emoji glyph per emotion. To show AIVA's eyes and mouth instead:

* Port `web/src/face/procedural.ts`, `engine.ts` and `framebuffer.ts` to C++ (they're
  dependency-free on purpose; the eyes are pycozmo's procedural face, which was designed for
  Cozmo's identical 128×64 OLED).
* Hook it into the firmware's `OledDisplay::SetEmotion()` and drive the mouth from the
  speaker level, running at ~20 fps on the S3's second core.
* The server already sends everything the face needs (`llm` emotion per sentence, `tts`
  start/stop for speaking mode); the `aiva` extensions (animations, VAD) can be enabled by
  sending `features.aiva = true` in the device hello.
