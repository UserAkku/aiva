import { CheckCircle2, ExternalLink, KeyRound, Mail, Plus, Server, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorNote, Input, Meter, PageHeader, Toggle } from "../components/ui";
import { api, pct, type Connectors, type Provider } from "../lib/api";
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

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-[18px]" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.9z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.9z" />
    </svg>
  );
}

const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Google sends the user back to AIVA; the server redirects to #/connectors?google=connected|error. */
function readGoogleResult(): { ok: boolean; text: string } | null {
  const params = new URLSearchParams(location.hash.split("?")[1] ?? "");
  const flag = params.get("google");
  if (flag === "connected") return { ok: true, text: `Gmail connected with Google as ${params.get("account") || "your account"}.` };
  if (flag === "error") return { ok: false, text: params.get("message") || "Google sign-in didn't finish. Please try again." };
  return null;
}

function GmailCard({ data, onChange }: { data?: Connectors["gmail"]; onChange: () => void }) {
  const [result] = useState(readGoogleResult);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [googleMsg, setGoogleMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [clientJson, setClientJson] = useState("");
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [appBusy, setAppBusy] = useState(false);
  const [appMsg, setAppMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const google = data?.google;
  const letters = password.replace(/[\s-]/g, "");
  const appPasswordOk = /^[A-Za-z]{16}$/.test(letters);

  // The result banner is read once; clear the query so a refresh doesn't show it again.
  useEffect(() => {
    if (location.hash.includes("google=")) history.replaceState(null, "", `${location.pathname}${location.search}#/connectors`);
  }, []);

  const signIn = async () => {
    setGoogleBusy(true);
    setGoogleMsg(null);
    try {
      const { url } = await api.googleStart();
      window.location.href = url; // Google's consent page; it returns to AIVA by itself
    } catch (e) {
      setGoogleMsg({ ok: false, text: errorText(e) });
      setGoogleBusy(false);
    }
  };

  const saveClient = async () => {
    setGoogleBusy(true);
    setGoogleMsg(null);
    try {
      await api.googleSetClient(clientJson.trim());
      setClientJson("");
      setGoogleMsg({ ok: true, text: "Saved. Now click Continue with Google." });
      onChange();
    } catch (e) {
      setGoogleMsg({ ok: false, text: errorText(e) });
    } finally {
      setGoogleBusy(false);
    }
  };

  const connectApp = async () => {
    setAppBusy(true);
    setAppMsg(null);
    try {
      const res = await api.connectGmail(address.trim(), password);
      setAppMsg({ ok: true, text: res.message });
      setPassword("");
      onChange();
    } catch (e) {
      setAppMsg({ ok: false, text: errorText(e) });
    } finally {
      setAppBusy(false);
    }
  };

  const disconnect = async () => {
    if (data?.method === "google") await api.googleDisconnect();
    else await api.disconnectGmail();
    onChange();
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Mail className="size-4 text-rose-300" /> Gmail{" "}
          {data?.configured ? <Badge tone="green">{data.account}</Badge> : <Badge>not connected</Badge>}
        </span>
      }
      subtitle="Lets AIVA check, search, read and, after your spoken yes, send email."
      actions={
        data?.configured && (
          <Button variant="danger" onClick={() => void disconnect()}>
            Disconnect
          </Button>
        )
      }
    >
      {result && (
        <p
          className={`mb-4 rounded-xl border px-3 py-2 text-[12.5px] ${
            result.ok
              ? "border-emerald-400/20 bg-emerald-500/[0.07] text-emerald-200"
              : "border-rose-400/20 bg-rose-500/[0.07] text-rose-200"
          }`}
        >
          {result.text}
        </p>
      )}

      {google?.connected ? (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-400/15 bg-emerald-500/[0.06] px-4 py-3.5">
          <CheckCircle2 className="size-5 shrink-0 text-emerald-300" />
          <div className="min-w-0">
            <div className="text-[13.5px] text-zinc-100">Signed in with Google</div>
            <div className="truncate font-mono text-[12px] text-zinc-400">{google.email}</div>
          </div>
        </div>
      ) : !google?.client_configured ? (
        <div className="space-y-4">
          <div>
            <div className="text-[13.5px] font-medium text-zinc-100">One-time setup · about 5 minutes</div>
            <p className="mt-1 text-[12.5px] text-zinc-500">
              Google needs to know AIVA is allowed to ask. Do this once; after that, connecting is one click.
            </p>
          </div>
          <ol className="list-decimal space-y-2 pl-5 text-[13px] text-zinc-400">
            <li>
              Create a project (any name):{" "}
              <a className="text-cyan-300 hover:underline" href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noreferrer">
                New project
              </a>
              .
            </li>
            <li>
              Turn on Gmail for it:{" "}
              <a
                className="text-cyan-300 hover:underline"
                href="https://console.cloud.google.com/apis/enableflow;apiid=gmail.googleapis.com"
                target="_blank"
                rel="noreferrer"
              >
                Enable the Gmail API
              </a>
              .
            </li>
            <li>
              Open{" "}
              <a className="text-cyan-300 hover:underline" href="https://console.developers.google.com/auth/branding" target="_blank" rel="noreferrer">
                Google Auth platform → Branding
              </a>
              , click <b className="text-zinc-200">Get started</b>, fill in an app name and your email, and choose{" "}
              <b className="text-zinc-200">External</b>. Then under{" "}
              <a className="text-cyan-300 hover:underline" href="https://console.developers.google.com/auth/audience" target="_blank" rel="noreferrer">
                Audience → Test users
              </a>{" "}
              add your own Gmail address.
            </li>
            <li>
              Open{" "}
              <a className="text-cyan-300 hover:underline" href="https://console.developers.google.com/auth/clients" target="_blank" rel="noreferrer">
                Clients
              </a>{" "}
              → <b className="text-zinc-200">Create client</b> → application type <b className="text-zinc-200">Desktop app</b> → Create.
            </li>
            <li>Download the JSON file and paste its whole contents below.</li>
          </ol>
          <textarea
            value={clientJson}
            onChange={(e) => setClientJson(e.target.value)}
            rows={4}
            spellCheck={false}
            placeholder='{"installed": {"client_id": "…apps.googleusercontent.com", "client_secret": "…"}}'
            className="w-full rounded-xl border border-white/[0.08] bg-black/40 p-3 font-mono text-[12px] text-zinc-200 outline-none transition placeholder:text-zinc-600 focus:border-cyan-300/40 focus:ring-4 focus:ring-cyan-300/10"
          />
          <Button variant="primary" busy={googleBusy} disabled={clientJson.trim().length < 20} onClick={() => void saveClient()}>
            Save setup
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <button
            type="button"
            disabled={googleBusy}
            onClick={() => void signIn()}
            className="inline-flex w-full items-center justify-center gap-3 rounded-xl bg-white px-4 py-3 text-[14px] font-medium text-zinc-900 shadow-[0_0_0_1px_rgba(255,255,255,0.6),0_8px_24px_-8px_rgba(255,255,255,0.35)] transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <GoogleMark /> {googleBusy ? "Opening Google…" : "Continue with Google"}
          </button>
          <p className="text-center text-[12px] text-zinc-500">
            Pick the Gmail account AIVA should use, then keep the Gmail box ticked on Google's screen.
          </p>
          {google?.expired && (
            <p className="rounded-xl border border-amber-300/20 bg-amber-400/[0.06] px-3 py-2 text-[12.5px] text-amber-100">
              Your last Google connection expired. Apps in Testing mode need a fresh sign-in about every 7 days. Click
              Continue with Google again.
            </p>
          )}
        </div>
      )}
      {googleMsg && <p className={`mt-3 text-[12.5px] ${googleMsg.ok ? "text-emerald-300" : "text-rose-300"}`}>{googleMsg.text}</p>}

      <details className="mt-5 rounded-xl border border-white/[0.06] bg-black/15 px-4 py-3">
        <summary className="cursor-pointer select-none text-[12.5px] text-zinc-400 hover:text-zinc-200">
          Advanced · connect with an App Password instead
        </summary>
        <div className="mt-4 grid gap-5 md:grid-cols-2">
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
              Paste your Gmail address and the <b className="text-zinc-200">16-letter</b> App Password here, not your normal
              Gmail password.
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
            <Button variant="subtle" busy={appBusy} disabled={!address.includes("@") || !appPasswordOk} onClick={() => void connectApp()}>
              <CheckCircle2 className="size-4" /> Connect & test
            </Button>
            {appMsg && <p className={`text-[12.5px] ${appMsg.ok ? "text-emerald-300" : "text-rose-300"}`}>{appMsg.text}</p>}
          </div>
        </div>
      </details>
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
