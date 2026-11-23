import clsx from "clsx";
import { Activity, Brain, Cpu, Gauge, Plug, Radio, Settings, Wrench } from "lucide-react";
import { type ComponentType, type ReactNode, useEffect, useState } from "react";
import { StatusDot } from "./components/ui";
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

type Page = { id: string; label: string; icon: ComponentType<{ className?: string }>; render: (status: Status | null, reload: () => void) => ReactNode };

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

function Shell() {
  const route = useHashRoute();
  const { state } = useDevice();
  const { data: status, reload } = useLoad(api.status, [], 5000);
  const page = PAGES.find((p) => p.id === route) ?? PAGES[0];

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-white/6 bg-black/20 px-3 py-5">
        <a href="#/live" className="mb-7 flex items-center gap-3 px-2">
          <div className="grid size-10 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400 to-violet-500 text-lg font-black text-zinc-950 shadow-lg shadow-cyan-500/20">
            ◕‿◕
          </div>
          <div>
            <div className="text-[17px] font-bold tracking-tight text-white">{status?.assistant.name ?? "AIVA"}</div>
            <div className="text-[11px] text-zinc-500">voice desk buddy · v{status?.version ?? "…"}</div>
          </div>
        </a>
        <nav className="flex flex-col gap-1">
          {PAGES.map((p) => (
            <a
              key={p.id}
              href={`#/${p.id}`}
              className={clsx(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-[13.5px] transition",
                p.id === page.id ? "bg-white/8 text-white" : "text-zinc-400 hover:bg-white/4 hover:text-zinc-200",
              )}
            >
              <p.icon className="size-4" />
              {p.label}
            </a>
          ))}
        </nav>
        <div className="mt-auto space-y-2 rounded-2xl border border-white/6 bg-white/[0.02] p-3 text-[12px] text-zinc-400">
          <div className="flex items-center justify-between">
            <span>Device</span>
            <span className="flex items-center gap-1.5">
              <StatusDot status={state === "offline" ? "fail" : state === "connecting" ? "warn" : "ok"} /> {state}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>AI brain</span>
            <span className="flex items-center gap-1.5">
              <StatusDot status={status?.llm_ready ? "ok" : "fail"} /> {status?.llm_ready ? "ready" : "no key"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Free quota</span>
            <span>{status?.pool_fraction == null ? "—" : `${Math.round(status.pool_fraction * 100)}% left`}</span>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-8 py-7">{page.render(status, reload)}</div>
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
