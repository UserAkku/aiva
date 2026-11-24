/** Thin typed wrappers around the dashboard REST API. */

export interface QuotaMetric {
  remaining: number | null;
  limit: number | null;
}

export interface DeploymentState {
  id: string;
  provider: string;
  model: string;
  priority: number;
  has_key: boolean;
  metrics: Record<"rpm" | "rpd" | "tpm" | "tpd", QuotaMetric>;
  daily_fraction: number | null;
  cooldown_s: number;
  cooldown_reason: string;
  requests: number;
  errors: number;
  last_error: string | null;
  last_latency_ms: number | null;
  status: "ready" | "cooldown" | "low" | "no-key";
}

export interface Provider {
  name: string;
  label: string;
  key_env: string;
  key_set: boolean;
  key_hint: string | null;
  signup_url: string;
  free_tier: string;
  kind: "llm" | "voice";
  deployments: Array<{
    id: string;
    model: string;
    priority: number;
    enabled: boolean;
    limits: Record<string, number | null>;
    state?: DeploymentState;
    build_error?: string;
  }>;
}

export interface Status {
  version: string;
  uptime_s: number;
  assistant: { name: string; owner_name: string; language: string; city: string; personality: string };
  llm_ready: boolean;
  stt_ready: boolean;
  pool_fraction: number | null;
  deployments: DeploymentState[];
  devices: Array<Record<string, any>>;
  connectors: Connectors;
  esp32: { websocket: string; ota: string };
}

export interface Connectors {
  gmail: { configured: boolean; account: string; error: string | null };
  mcp: Array<{ name: string; transport: string; target: string; enabled: boolean; error: string | null; tools: string[] }>;
  mcp_presets: Record<string, { description: string; config: Record<string, unknown> }>;
}

export interface ToolCategory {
  name: string;
  description: string;
  always: boolean;
  keywords: string[];
  tools: Array<{ name: string; enabled: boolean; confirm: boolean; description: string }>;
}

export interface Check {
  name: string;
  status: "ok" | "warn" | "fail";
  detail: string;
  group: string;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<Status>("GET", "/api/status"),
  doctor: (deep = false) => request<{ status: string; checks: Check[] }>("GET", `/api/doctor?deep=${deep}`),
  usage: () => request<{ deployments: DeploymentState[]; pool_fraction: number | null; history: any[]; turns: any[] }>("GET", "/api/usage"),
  activity: () => request<any[]>("GET", "/api/activity"),
  providers: () => request<Provider[]>("GET", "/api/providers"),
  setKey: (provider: string, key: string) => request<{ ok: boolean; message: string }>("PUT", `/api/providers/${provider}/key`, { key }),
  deleteKey: (provider: string) => request("DELETE", `/api/providers/${provider}/key`),
  patchDeployment: (id: string, patch: { enabled?: boolean; priority?: number }) => request("PATCH", `/api/deployments/${id}`, patch),
  tools: () => request<ToolCategory[]>("GET", "/api/tools"),
  toggleTool: (name: string, enabled: boolean) => request("PUT", `/api/tools/${name}`, { enabled }),
  connectors: () => request<Connectors>("GET", "/api/connectors"),
  connectGmail: (address: string, app_password: string) =>
    request<{ ok: boolean; message: string }>("POST", "/api/connectors/gmail", { address, app_password }),
  disconnectGmail: () => request("DELETE", "/api/connectors/gmail"),
  addMcp: (name: string, config: Record<string, unknown>) => request<{ ok: boolean; name: string }>("POST", "/api/connectors/mcp", { name, config }),
  testMcp: (name: string) => request<{ ok: boolean; tools: string[] }>("POST", `/api/connectors/mcp/${name}/test`),
  removeMcp: (name: string) => request("DELETE", `/api/connectors/mcp/${name}`),
  settings: () => request<{ config: any; overrides: any }>("GET", "/api/settings"),
  saveSettings: (patch: Record<string, unknown>) => request<{ config: any }>("PUT", "/api/settings", patch),
  memory: () => request<{ facts: any[]; notes: any[]; todos: any[]; reminders: any[] }>("GET", "/api/memory"),
  addFact: (text: string) => request("POST", "/api/memory/facts", { text }),
  deleteMemory: (kind: string, id: number) => request("DELETE", `/api/memory/${kind}/${id}`),
  doneTodo: (id: number) => request("POST", `/api/memory/todos/${id}/done`),
  resetConversation: () => request("POST", "/api/conversation/reset"),
  voices: () => request<Array<{ name: string; locale: string; gender: string }>>("GET", "/api/tts/voices"),
  previewVoice: async (text: string, voice?: string): Promise<Blob> => {
    const res = await fetch("/api/tts/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.blob();
  },
};

export function pct(fraction: number | null | undefined): string {
  return fraction == null ? "—" : `${Math.round(fraction * 100)}%`;
}
