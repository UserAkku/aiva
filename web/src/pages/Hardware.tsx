import { TriangleAlert } from "lucide-react";
import { Badge, Card, PageHeader } from "../components/ui";
import type { Status } from "../lib/api";

const WIRING = [
  ["INMP441 mic", "WS", "GPIO 4"],
  ["INMP441 mic", "SCK", "GPIO 5"],
  ["INMP441 mic", "SD", "GPIO 6"],
  ["INMP441 mic", "L/R", "GND (left channel)"],
  ["INMP441 mic", "VDD / GND", "3V3 / GND"],
  ["MAX98357A amp", "DIN", "GPIO 7"],
  ["MAX98357A amp", "BCLK", "GPIO 15"],
  ["MAX98357A amp", "LRC", "GPIO 16"],
  ["MAX98357A amp", "VIN / GND", "5V / GND"],
  ["SSD1306 OLED", "SDA", "GPIO 41"],
  ["SSD1306 OLED", "SCL", "GPIO 42"],
  ["SSD1306 OLED", "VCC / GND", "3V3 / GND"],
  ["Boot button", "—", "GPIO 0 (talk / wake)"],
];

export function HardwarePage({ status }: { status: Status | null }) {
  const esp = status?.devices.filter((d) => d.kind === "esp32") ?? [];
  return (
    <>
      <PageHeader
        title="Hardware (phase 2)"
        subtitle="AIVA's body: ESP32-S3 + I²S mic + MAX98357A amp + SSD1306 OLED, running the open-source xiaozhi-esp32 firmware (board: bread-compact-wifi-128x64) pointed at this Mac."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Connect an ESP32 to this server">
          <dl className="space-y-3 text-[13px]">
            <div>
              <dt className="text-zinc-500">OTA / config URL (set in firmware menuconfig)</dt>
              <dd className="font-mono text-cyan-200">{status?.esp32.ota ?? "…"}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">WebSocket the device will be told to use</dt>
              <dd className="font-mono text-cyan-200">{status?.esp32.websocket ?? "…"}</dd>
            </div>
            <div>
              <dt className="text-zinc-500">Connected hardware devices</dt>
              <dd>{esp.length ? esp.map((d) => <Badge key={d.session} tone="green">{d.device_id} · {d.state}</Badge>) : <span className="text-zinc-400">none yet — the browser simulator is standing in</span>}</dd>
            </div>
          </dl>
          <p className="mt-4 text-[12.5px] text-zinc-400">
            The Mac and the ESP32 must be on the same Wi-Fi. The protocol is identical to the simulator's, so nothing changes on the server side — see <code>docs/HARDWARE.md</code>.
          </p>
        </Card>

        <Card title="Your parts — one change needed">
          <div className="space-y-3 text-[13px] text-zinc-300">
            <p className="flex gap-2 rounded-xl bg-rose-500/10 p-3 text-rose-100">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <span>
                <b>KY-038 (LM393) is a sound-level detector, not a voice microphone.</b> Its analog output is too noisy and
                low-fidelity for speech-to-text. Use an <b>INMP441 I²S MEMS mic</b> (≈₹150–250) — it's what the firmware expects.
                Keep the KY-038 for a clap-to-wake trick if you like.
              </span>
            </p>
            <p className="flex gap-2 rounded-xl bg-amber-500/10 p-3 text-amber-100">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <span>
                The <b>0.25 W coin speaker</b> can be damaged by a MAX98357A at full volume (it can deliver ~1.8 W into 8 Ω at 5 V).
                Tie the amp's GAIN pin to VDD through 100 kΩ (lowest gain) and keep the firmware volume ≤ 60%.
              </span>
            </p>
            <p>✅ ESP32-S3 (N16R8 recommended), ✅ MAX98357A, ✅ 0.96″ SSD1306 128×64 I²C OLED.</p>
          </div>
        </Card>

        <Card title="Wiring (xiaozhi bread-compact-wifi pin map)" className="lg:col-span-2">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="py-2">Module</th>
                <th className="py-2">Pin</th>
                <th className="py-2">ESP32-S3</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {WIRING.map(([m, p, g]) => (
                <tr key={m + p}>
                  <td className="py-2 text-zinc-300">{m}</td>
                  <td className="py-2 font-mono text-zinc-400">{p}</td>
                  <td className="py-2 font-mono text-cyan-200">{g}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}
