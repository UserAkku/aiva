import { Badge, Card, ErrorNote, Meter, PageHeader } from "../components/ui";
import { api, type DeploymentState, pct } from "../lib/api";
import { useLoad } from "../lib/hooks";

const fmt = (n: number | null | undefined) => (n == null ? "—" : n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K` : String(n));

function frac(m: { remaining: number | null; limit: number | null }): number | null {
  return m.remaining == null || !m.limit ? null : m.remaining / m.limit;
}

export function UsagePage() {
  const { data, error } = useLoad(api.usage, [], 3000);
  const keyed = data?.deployments.filter((d) => d.has_key) ?? [];
  return (
    <>
      <PageHeader
        title="Usage & limits"
        subtitle="Live free-tier quota per model, read from provider rate-limit headers plus local accounting. AIVA warns out loud at 25% and 10%."
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Today's free quota (pooled)">
          <div className="text-4xl font-semibold text-white">{pct(data?.pool_fraction)}</div>
          <div className="mt-3">
            <Meter value={data?.pool_fraction ?? null} />
          </div>
          <p className="mt-2 text-[12px] text-zinc-500">Across all providers that publish a daily limit.</p>
        </Card>
        <Card title="Models ready">
          <div className="text-4xl font-semibold text-white">
            {keyed.filter((d) => d.status === "ready").length}
            <span className="text-xl text-zinc-500"> / {keyed.length}</span>
          </div>
          <p className="mt-2 text-[12px] text-zinc-500">Cooling-down models are skipped automatically.</p>
        </Card>
        <Card title="Requests this session">
          <div className="text-4xl font-semibold text-white">{keyed.reduce((n, d) => n + d.requests, 0)}</div>
          <p className="mt-2 text-[12px] text-zinc-500">{keyed.reduce((n, d) => n + d.errors, 0)} errors / fallbacks</p>
        </Card>
      </div>

      <Card className="mt-4" title="Per model">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="py-2 pr-4">Model</th>
                <th className="py-2 pr-4">Status</th>
                <th className="w-44 py-2 pr-4">Requests / day</th>
                <th className="w-44 py-2 pr-4">Tokens / minute</th>
                <th className="py-2 pr-4">Latency</th>
                <th className="py-2">Errors</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {(data?.deployments ?? []).map((d: DeploymentState) => (
                <tr key={d.id} className={d.has_key ? "" : "opacity-40"}>
                  <td className="py-2.5 pr-4">
                    <div className="font-mono text-[12.5px] text-zinc-200">{d.model}</div>
                    <div className="text-[11px] text-zinc-500">{d.provider}</div>
                  </td>
                  <td className="py-2.5 pr-4">
                    <Badge tone={d.status === "ready" ? "green" : d.status === "cooldown" ? "amber" : d.status === "low" ? "rose" : "zinc"}>{d.status}</Badge>
                    {d.cooldown_s > 0 && <div className="mt-1 text-[11px] text-amber-300">{Math.ceil(d.cooldown_s)}s · {d.cooldown_reason}</div>}
                  </td>
                  <td className="py-2.5 pr-4">
                    <Meter value={frac(d.metrics.rpd)} hint={`${fmt(d.metrics.rpd.remaining)} / ${fmt(d.metrics.rpd.limit)}`} />
                  </td>
                  <td className="py-2.5 pr-4">
                    <Meter value={frac(d.metrics.tpm)} hint={`${fmt(d.metrics.tpm.remaining)} / ${fmt(d.metrics.tpm.limit)}`} />
                  </td>
                  <td className="py-2.5 pr-4 text-zinc-300">{d.last_latency_ms ? `${Math.round(d.last_latency_ms)} ms` : "—"}</td>
                  <td className="py-2.5 text-zinc-300" title={d.last_error ?? ""}>
                    {d.errors}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="mt-4" title="Recent turns" subtitle="Latency breakdown per voice turn (speech-to-text → first LLM token → first audio).">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="py-2 pr-4">When</th>
                <th className="py-2 pr-4">You said</th>
                <th className="py-2 pr-4">Model</th>
                <th className="py-2 pr-4">Tools</th>
                <th className="py-2 pr-4">STT</th>
                <th className="py-2 pr-4">1st token</th>
                <th className="py-2">1st audio</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {(data?.turns ?? []).map((t) => (
                <tr key={t.id}>
                  <td className="whitespace-nowrap py-2 pr-4 text-zinc-500">{new Date(t.created_at * 1000).toLocaleTimeString()}</td>
                  <td className="max-w-80 truncate py-2 pr-4 text-zinc-200" title={t.user_text}>
                    {t.user_text}
                  </td>
                  <td className="py-2 pr-4 font-mono text-[12px] text-zinc-400">{t.model ?? "—"}</td>
                  <td className="py-2 pr-4 text-[12px] text-amber-200/80">{(t.tools as string[]).join(", ") || "—"}</td>
                  <td className="py-2 pr-4 text-zinc-300">{t.timings.stt_ms ? `${Math.round(t.timings.stt_ms)} ms` : "—"}</td>
                  <td className="py-2 pr-4 text-zinc-300">{t.timings.llm_first_token_ms ? `${Math.round(t.timings.llm_first_token_ms)} ms` : "—"}</td>
                  <td className="py-2 text-zinc-300">{t.timings.first_audio_ms ? `${Math.round(t.timings.first_audio_ms)} ms` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data?.turns.length === 0 && <p className="py-4 text-[13px] text-zinc-500">No voice turns yet.</p>}
        </div>
      </Card>
    </>
  );
}
