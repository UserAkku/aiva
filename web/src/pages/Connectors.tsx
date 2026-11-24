import { CheckCircle2, ExternalLink, KeyRound, Mail, Plus, Server, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorNote, Input, Meter, PageHeader, Toggle } from "../components/ui";
import { api, pct, type Provider } from "../lib/api";
import { useLoad } from "../lib/hooks";

export function ConnectorsPage({ onChange }: { onChange: () => void }) {
  const providers = useLoad(api.providers, [], 6000);
  const connectors = useLoad(api.connectors, []);

  return (
    <>
      <PageHeader
        title="Connectors"
        subtitle="Plug AIVA into AI brains, your accounts and external tool servers. Keys stay on this Mac (.env / data/), never in git."
      />
      <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-zinc-500">AI brains · free tiers</h2>
      <p className="mb-4 max-w-3xl text-[13px] text-zinc-400">
        Add as many free keys as you can — AIVA's quota-aware router spreads requests across all of them and switches
        instantly when one hits its limit, so a live demo never stalls. <b className="text-zinc-200">Groq is required</b> (it
        also powers speech-to-text); Mistral and Gemini are strongly recommended backups.
      </p>
      {providers.error && <ErrorNote>{providers.error}</ErrorNote>}
      <div className="grid gap-4 lg:grid-cols-2">
        {providers.data?.filter((p) => p.kind !== "voice").map((p) => (
          <ProviderCard
            key={p.name}
            provider={p}
            onChange={() => {
              void providers.reload();
              onChange();
            }}
          />
        ))}
      </div>

      <h2 className="mb-3 mt-10 text-[13px] font-semibold uppercase tracking-wider text-zinc-500">Voice</h2>
      <p className="mb-4 max-w-3xl text-[13px] text-zinc-400">
        Without a key AIVA uses free Microsoft Edge voices. Add a free <b className="text-zinc-200">Sarvam</b> key for Indian
        "companion" voices built for Hinglish — they sound like a real person and change tone with AIVA's emotions.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        {providers.data?.filter((p) => p.kind === "voice").map((p) => (
          <ProviderCard
            key={p.name}
            provider={p}
            onChange={() => {
              void providers.reload();
              onChange();
            }}
          />
        ))}
      </div>

      <h2 className="mb-3 mt-10 text-[13px] font-semibold uppercase tracking-wider text-zinc-500">Accounts</h2>
      <GmailCard data={connectors.data?.gmail} onChange={() => void connectors.reload()} />

      <h2 className="mb-3 mt-10 text-[13px] font-semibold uppercase tracking-wider text-zinc-500">MCP tool servers</h2>
      <McpCard data={connectors.data} onChange={() => void connectors.reload()} />
    </>
  );
}

function ProviderCard({ provider: p, onChange }: { provider: Provider; onChange: () => void }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.setKey(p.name, key.trim());
      setMsg({ ok: res.ok, text: res.message });
      if (res.ok) setKey("");
      onChange();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          {p.label}
          {p.key_set ? <Badge tone="green">connected</Badge> : p.name === "groq" ? <Badge tone="rose">required</Badge> : <Badge>optional</Badge>}
        </span>
      }
      subtitle={p.free_tier}
      actions={
        <a href={p.signup_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] text-cyan-300 hover:underline">
          Get free key <ExternalLink className="size-3" />
        </a>
      }
    >
      <div className="flex gap-2">
        <div className="relative flex-1">
          <KeyRound className="absolute left-3 top-2.5 size-4 text-zinc-500" />
          <Input
            type="password"
            className="pl-9"
            placeholder={p.key_set ? `saved (${p.key_hint}) — paste to replace` : `${p.key_env}`}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && key.trim().length >= 8 && void save()}
          />
        </div>
        <Button variant="primary" busy={busy} disabled={key.trim().length < 8} onClick={() => void save()}>
          Save & test
        </Button>
        {p.key_set && (
          <Button
            variant="ghost"
            title="Remove key"
            onClick={async () => {
              await api.deleteKey(p.name);
              onChange();
            }}
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>
      {msg && <p className={`mt-2 text-[12.5px] ${msg.ok ? "text-emerald-300" : "text-rose-300"}`}>{msg.text}</p>}
      <div className="mt-4 space-y-2.5">
        {p.deployments.map((d) => (
          <div key={d.id} className="rounded-xl border border-white/6 bg-black/20 px-3 py-2.5">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-mono text-[12.5px] text-zinc-200">{d.model}</div>
                <div className="text-[11px] text-zinc-500">
                  priority {d.priority}
                  {d.limits.rpd ? ` · ${d.limits.rpd} req/day` : ""}
                  {d.limits.tpm ? ` · ${(d.limits.tpm / 1000).toFixed(0)}K tok/min` : ""}
                  {d.state?.last_latency_ms ? ` · ${Math.round(d.state.last_latency_ms)} ms` : ""}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {d.state && p.key_set && (
                  <Badge tone={d.state.status === "ready" ? "green" : d.state.status === "cooldown" ? "amber" : d.state.status === "low" ? "rose" : "zinc"}>
                    {d.state.status}
                  </Badge>
                )}
                <Toggle
                  checked={d.enabled}
                  onChange={async (v) => {
                    await api.patchDeployment(d.id, { enabled: v });
                    onChange();
                  }}
                />
              </div>
            </div>
            {p.key_set && d.state && d.enabled && (
              <div className="mt-2">
                <Meter value={d.state.daily_fraction} hint={`${pct(d.state.daily_fraction)} of today's quota left`} />
              </div>
            )}
            {d.state?.last_error && <p className="mt-1.5 truncate text-[11px] text-rose-300/80" title={d.state.last_error}>{d.state.last_error}</p>}
            {d.build_error && <p className="mt-1.5 text-[11px] text-rose-300/80">{d.build_error}</p>}
          </div>
        ))}
      </div>
    </Card>
  );
}

function GmailCard({ data, onChange }: { data?: { configured: boolean; account: string; error: string | null }; onChange: () => void }) {
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const letters = password.replace(/[\s-]/g, "");
  const appPasswordOk = /^[A-Za-z]{16}$/.test(letters);

  const connect = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.connectGmail(address.trim(), password);
      setMsg({ ok: true, text: res.message });
      setPassword("");
      onChange();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Mail className="size-4 text-rose-300" /> Gmail {data?.configured ? <Badge tone="green">{data.account}</Badge> : <Badge>not connected</Badge>}
        </span>
      }
      subtitle="Lets AIVA check, search, read and (after your spoken yes) send email. Uses a Google App Password — no Google Cloud setup."
      actions={
        data?.configured && (
          <Button
            variant="danger"
            onClick={async () => {
              await api.disconnectGmail();
              onChange();
            }}
          >
            Disconnect
          </Button>
        )
      }
    >
      <div className="grid gap-5 md:grid-cols-2">
        <ol className="list-decimal space-y-1.5 pl-5 text-[13px] text-zinc-400">
          <li>
            Turn on <b className="text-zinc-200">2-Step Verification</b> in your Google Account.
          </li>
          <li>
            Open{" "}
            <a className="text-cyan-300 hover:underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">
              App passwords
            </a>{" "}
            and create one named "AIVA".
          </li>
          <li>
            Paste your Gmail address and the <b className="text-zinc-200">16-letter</b> App Password here — not your
            normal Gmail password. Create it while signed in to the <b className="text-zinc-200">same</b> account.
          </li>
        </ol>
        <div className="space-y-2">
          <Input placeholder="you@gmail.com" value={address} onChange={(e) => setAddress(e.target.value)} />
          <Input type="password" placeholder="abcd efgh ijkl mnop" value={password} onChange={(e) => setPassword(e.target.value)} />
          {password && (
            <p className={`font-mono text-[11px] ${appPasswordOk ? "text-emerald-300" : "text-amber-300"}`}>
              {appPasswordOk
                ? "✓ looks like an App Password"
                : `${letters.length}/16 letters — an App Password is exactly 16 letters (spaces don't matter)`}
            </p>
          )}
          <Button variant="primary" busy={busy} disabled={!address.includes("@") || !appPasswordOk} onClick={() => void connect()}>
            <CheckCircle2 className="size-4" /> Connect & test
          </Button>
          {msg && <p className={`text-[12.5px] ${msg.ok ? "text-emerald-300" : "text-rose-300"}`}>{msg.text}</p>}
        </div>
      </div>
    </Card>
  );
}

function McpCard({ data, onChange }: { data?: Awaited<ReturnType<typeof api.connectors>> | null; onChange: () => void }) {
  const [name, setName] = useState("");
  const [config, setConfig] = useState('{\n  "command": "npx",\n  "args": ["-y", "@playwright/mcp@latest"]\n}');
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const add = async () => {
    setMsg(null);
    setBusy("add");
    try {
      const parsed = JSON.parse(config);
      const res = await api.addMcp(name.trim(), parsed);
      setMsg({ ok: true, text: `Added "${res.name}". Press Test to connect and list its tools.` });
      setName("");
      onChange();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const test = async (server: string) => {
    setBusy(server);
    setMsg(null);
    try {
      const res = await api.testMcp(server);
      setMsg({ ok: true, text: `${server}: ${res.tools.length} tools — ${res.tools.slice(0, 12).join(", ")}${res.tools.length > 12 ? "…" : ""}` });
      onChange();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Server className="size-4 text-violet-300" /> Model Context Protocol servers
        </span>
      }
      subtitle="Add any MCP server (same JSON as Claude Desktop / Cursor). Its tools become a new AIVA skill — e.g. Playwright lets AIVA drive a real browser."
    >
      <div className="space-y-2">
        {data?.mcp.length === 0 && <p className="text-[13px] text-zinc-500">No servers yet.</p>}
        {data?.mcp.map((s) => (
          <div key={s.name} className="flex items-center justify-between gap-3 rounded-xl border border-white/6 bg-black/20 px-3 py-2.5">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-200">
                {s.name} <Badge tone="violet">{s.transport}</Badge> {s.tools.length > 0 && <Badge tone="green">{s.tools.length} tools</Badge>}
              </div>
              <div className="truncate font-mono text-[11px] text-zinc-500">{s.target}</div>
              {s.error && <div className="truncate text-[11px] text-rose-300">{s.error}</div>}
            </div>
            <div className="flex gap-2">
              <Button busy={busy === s.name} onClick={() => void test(s.name)}>
                Test
              </Button>
              <Button
                variant="ghost"
                onClick={async () => {
                  await api.removeMcp(s.name);
                  onChange();
                }}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-[1fr_1.2fr]">
        <div className="space-y-2">
          <div className="text-[12px] font-medium text-zinc-400">Presets</div>
          {Object.entries(data?.mcp_presets ?? {}).map(([preset, info]) => (
            <button
              key={preset}
              onClick={() => {
                setName(preset);
                setConfig(JSON.stringify(info.config, null, 2));
              }}
              className="block w-full rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-left hover:bg-white/[0.06]"
            >
              <div className="text-[13px] font-medium text-zinc-200">{preset}</div>
              <div className="text-[12px] text-zinc-500">{info.description}</div>
            </button>
          ))}
        </div>
        <div className="space-y-2">
          <Input placeholder="name, e.g. playwright" value={name} onChange={(e) => setName(e.target.value)} />
          <textarea
            value={config}
            onChange={(e) => setConfig(e.target.value)}
            rows={7}
            spellCheck={false}
            className="w-full rounded-xl border border-white/10 bg-black/30 p-3 font-mono text-[12px] text-zinc-200 outline-none focus:border-cyan-400/60"
          />
          <Button variant="primary" busy={busy === "add"} disabled={!name.trim()} onClick={() => void add()}>
            <Plus className="size-4" /> Add server
          </Button>
        </div>
      </div>
      {msg && <p className={`mt-3 text-[12.5px] ${msg.ok ? "text-emerald-300" : "text-rose-300"}`}>{msg.text}</p>}
    </Card>
  );
}
