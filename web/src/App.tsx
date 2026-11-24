import clsx from "clsx";
import { Activity, Brain, Cpu, Gauge, Plug, Radio, Settings, Wrench } from "lucide-react";
import { type ComponentType, type ReactNode, useEffect, useState } from "react";
import { DeviceProvider, useDevice } from "./device/DeviceContext";
import { api, type Status } from "./lib/api";
import { useLoad } from "./lib/hooks";
import { ActivityPage } from "./pages/Activity";
import { ConnectorsPage } from "./pages/Connectors";
import { HardwarePage } from "./pages/Hardware";
import { LivePage } from "./pages/Live";
import { MemoryPage } from "./pages/Memory";
import { SettingsPage } from "./pages/Settings";
import { ToolsPage } from "./pages/Tools";
import { UsagePage } from "./pages/Usage";

type Page = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  render: (status: Status | null, reload: () => void) => ReactNode;
};

const PAGES: Page[] = [
  { id: "live", label: "Live", icon: Radio, render: (s) => <LivePage status={s} /> },
  { id: "connectors", label: "Connectors", icon: Plug, render: (_s, reload) => <ConnectorsPage onChange={reload} /> },
  { id: "tools", label: "Skills", icon: Wrench, render: () => <ToolsPage /> },
  { id: "usage", label: "Usage & limits", icon: Gauge, render: () => <UsagePage /> },
  { id: "memory", label: "Memory", icon: Brain, render: () => <MemoryPage /> },
  { id: "settings", label: "Settings", icon: Settings, render: (_s, reload) => <SettingsPage onChange={reload} /> },
  { id: "activity", label: "Activity", icon: Activity, render: () => <ActivityPage /> },
  { id: "hardware", label: "Hardware", icon: Cpu, render: (s) => <HardwarePage status={s} /> },
];

function useHashRoute(): string {
  const read = () => location.hash.replace(/^#\/?/, "") || "live";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

/** Tiny OLED-face logo mark (two eyes + smile) that glows with the device state. */
function LogoMark() {
  return (
    <div className="relative grid size-10 place-items-center rounded-xl border border-white/10 bg-gradient-to-b from-zinc-800 to-zinc-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
      <div className="flex gap-[5px]">
        <span className="h-[9px] w-[7px] rounded-[2px] bg-[rgb(var(--state))] shadow-[0_0_8px_rgb(var(--state))] transition-colors duration-500" />
        <span className="h-[9px] w-[7px] rounded-[2px] bg-[rgb(var(--state))] shadow-[0_0_8px_rgb(var(--state))] transition-colors duration-500" />
      </div>
      <span className="absolute bottom-[9px] h-[2px] w-[8px] rounded-full bg-[rgb(var(--state))] opacity-80" />
    </div>
  );
}

function SysRow({ label, value, tone }: { label: string; value: string; tone: "ok" | "warn" | "fail" | "idle" }) {
  const dot = {
    ok: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]",
    warn: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]",
    fail: "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]",
    idle: "bg-zinc-500",
  }[tone];
  return (
    <div className="flex items-center justify-between font-mono text-[10.5px] uppercase tracking-[0.14em]">
      <span className="text-zinc-600">{label}</span>
      <span className="flex items-center gap-2 text-zinc-300">
        <span className={clsx("size-1.5 rounded-full", dot)} />
        {value}
      </span>
    </div>
  );
}

function Shell() {
  const route = useHashRoute();
  const { state } = useDevice();
  const { data: status, reload } = useLoad(api.status, [], 5000);
  const page = PAGES.find((p) => p.id === route) ?? PAGES[0];
  const quota = status?.pool_fraction;

  return (
    <div data-state={state} className="relative flex h-full">
      <div className="backdrop" />
      <aside className="relative z-10 flex w-[232px] shrink-0 flex-col border-r border-white/[0.05] bg-black/30 px-3 py-5 backdrop-blur-xl">
        <a href="#/live" className="mb-8 flex items-center gap-3 px-2">
          <LogoMark />
          <div>
            <div className="text-[16px] font-semibold tracking-[-0.01em] text-white">{status?.assistant.name ?? "AIVA"}</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-zinc-600">desk companion · v{status?.version ?? "…"}</div>
          </div>
        </a>
        <div className="label mb-2 px-3">Control</div>
        <nav className="flex flex-col gap-0.5">
          {PAGES.map((p) => {
            const active = p.id === page.id;
            return (
              <a
                key={p.id}
                href={`#/${p.id}`}
                className={clsx(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] transition",
                  active ? "bg-white/[0.06] text-white" : "text-zinc-500 hover:bg-white/[0.03] hover:text-zinc-200",
                )}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-[rgb(var(--state))] shadow-[0_0_10px_rgb(var(--state))]" />
                )}
                <p.icon className={clsx("size-[15px]", active ? "text-[rgb(var(--state))]" : "")} />
                {p.label}
              </a>
            );
          })}
        </nav>
        <div className="mt-auto space-y-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
          <div className="label mb-1">System</div>
          <SysRow label="Device" value={state} tone={state === "offline" ? "fail" : state === "connecting" ? "warn" : "ok"} />
          <SysRow label="Brain" value={status?.llm_ready ? "ready" : "no key"} tone={status?.llm_ready ? "ok" : "fail"} />
          <SysRow
            label="Quota"
            value={quota == null ? "—" : `${Math.round(quota * 100)}%`}
            tone={quota == null ? "idle" : quota > 0.25 ? "ok" : quota > 0.1 ? "warn" : "fail"}
          />
        </div>
      </aside>
      <main className="relative z-10 min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1440px] px-8 py-7">{page.render(status, reload)}</div>
      </main>
    </div>
  );
}

export function App() {
  return (
    <DeviceProvider>
      <Shell />
    </DeviceProvider>
  );
}
