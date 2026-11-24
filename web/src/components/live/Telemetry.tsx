import { useMemo } from "react";
import { useDevice } from "../../device/DeviceContext";
import type { Status } from "../../lib/api";
import { useEvents } from "../../lib/hooks";

function Readout({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-zinc-600">{label}</div>
      <div className={`mt-0.5 truncate font-mono text-[12.5px] ${accent ? "text-[rgb(var(--state))]" : "text-zinc-200"}`}>{value}</div>
    </div>
  );
}

const ms = (v?: number) => (v == null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`);

/** HUD strip: live state + the last turn's model and latency, read from the event bus. */
export function Telemetry({ status }: { status: Status | null }) {
  const { state } = useDevice();
  const events = useEvents(80);
  const last = useMemo(() => [...events].reverse().find((e) => e.type === "turn.assistant" && e.timings), [events]);
  const model = last?.deployment ? String(last.deployment).replace(/^groq-|^mistral-|^gemini-/, "") : "—";
  const quota = status?.pool_fraction;

  return (
    <div className="glass hud grid grid-cols-2 gap-x-6 gap-y-3 rounded-2xl px-5 py-3.5 sm:grid-cols-5">
      <div className="min-w-0">
        <div className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-zinc-600">State</div>
        <div className="mt-0.5 flex items-center gap-2 font-mono text-[12.5px] uppercase tracking-wider text-[rgb(var(--state))]">
          <span className="size-1.5 animate-breathe rounded-full bg-[rgb(var(--state))] shadow-[0_0_10px_rgb(var(--state))]" />
          {state}
        </div>
      </div>
      <Readout label="Brain" value={model} />
      <Readout label="First word" value={ms(last?.timings?.first_audio_ms)} />
      <Readout label="Hearing" value={ms(last?.timings?.stt_ms)} />
      <Readout label="Free quota" value={quota == null ? "—" : `${Math.round(quota * 100)}%`} accent={quota != null && quota < 0.25} />
    </div>
  );
}
