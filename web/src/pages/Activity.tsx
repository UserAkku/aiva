import clsx from "clsx";
import { useMemo, useState } from "react";
import { Card, PageHeader } from "../components/ui";
import { useEvents } from "../lib/hooks";

const TONE: Record<string, string> = {
  "turn.user": "text-cyan-300",
  "turn.assistant": "text-violet-300",
  "tool.start": "text-amber-300",
  "tool.end": "text-amber-200/70",
  "quota.warning": "text-rose-300",
  "quota.cooldown": "text-rose-300/80",
  error: "text-rose-400",
  "device.connected": "text-emerald-300",
  "device.disconnected": "text-zinc-400",
};

function describe(e: Record<string, any>): string {
  switch (e.type) {
    case "turn.user":
      return `🗣 ${e.text}`;
    case "turn.assistant":
      return `🤖 ${e.text}${e.deployment ? `  · ${e.deployment}` : ""}${e.timings?.total_ms ? ` · ${e.timings.total_ms} ms` : ""}${e.error ? ` · ⚠ ${e.error}` : ""}`;
    case "tool.start":
      return `⚙ ${e.name}(${JSON.stringify(e.args ?? {}).slice(0, 160)})`;
    case "tool.end":
      return `✓ ${e.name}: ${String(e.summary ?? "").slice(0, 200)}`;
    case "quota.warning":
      return `⚠ ${e.text}`;
    case "quota.cooldown":
      return `⏸ ${e.deployment} resting ${e.seconds}s — ${e.reason}`;
    case "device.state":
      return `${e.device} → ${e.state}`;
    default: {
      const { type: _t, ts: _ts, ...rest } = e;
      return JSON.stringify(rest).slice(0, 220);
    }
  }
}

export function ActivityPage() {
  const events = useEvents(500);
  const [hideStates, setHideStates] = useState(true);
  const shown = useMemo(
    () => events.filter((e) => !hideStates || !["device.state", "vad.start"].includes(e.type)).slice().reverse(),
    [events, hideStates],
  );
  return (
    <>
      <PageHeader
        title="Activity"
        subtitle="Everything happening inside AIVA, live: turns, tool calls, fallbacks, warnings, devices."
        actions={
          <label className="flex items-center gap-2 text-[13px] text-zinc-400">
            <input type="checkbox" checked={hideStates} onChange={(e) => setHideStates(e.target.checked)} /> hide state changes
          </label>
        }
      />
      <Card>
        <ul className="space-y-1 font-mono text-[12px]">
          {shown.map((e, i) => (
            <li key={`${e.ts}-${i}`} className="flex gap-3">
              <span className="shrink-0 text-zinc-600">{new Date(e.ts * 1000).toLocaleTimeString()}</span>
              <span className={clsx("w-36 shrink-0 truncate", TONE[e.type] ?? "text-zinc-400")}>{e.type}</span>
              <span className="min-w-0 break-words text-zinc-300">{describe(e)}</span>
            </li>
          ))}
          {shown.length === 0 && <li className="text-zinc-500">Waiting for events…</li>}
        </ul>
      </Card>
    </>
  );
}
