# Firmware (phase 2)

AIVA's body runs the open-source **[xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)**
firmware (MIT) with the `bread-compact-wifi` board profile (ESP32-S3 + INMP441 + MAX98357A
+ SSD1306 128×64). It is not vendored here: clone it into this folder when you start the
hardware phase (build artefacts are git-ignored).

```bash
git clone https://github.com/78/xiaozhi-esp32 firmware/xiaozhi-esp32
```

Then follow [docs/HARDWARE.md](../docs/HARDWARE.md): set the OTA URL shown on AIVA's
Hardware page, flash, and the device connects to this Mac automatically.
