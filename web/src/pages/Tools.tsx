import { ShieldCheck } from "lucide-react";
import { Badge, Card, ErrorNote, PageHeader, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useLoad } from "../lib/hooks";

export function ToolsPage() {
  const { data, error, reload } = useLoad(api.tools);
  const total = data?.reduce((n, c) => n + c.tools.length, 0) ?? 0;
  return (
    <>
      <PageHeader
        title="Skills"
        subtitle={`${total} built-in tools in ${data?.length ?? 0} skill groups. To save free-tier tokens AIVA only shows the model the skills that match what you said (keywords below) — or loads more on demand.`}
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {data?.map((cat) => (
          <Card
            key={cat.name}
            title={
              <span className="flex items-center gap-2 capitalize">
                {cat.name.replace(/^mcp_/, "MCP · ")} {cat.always ? <Badge tone="cyan">always on</Badge> : <Badge>on demand</Badge>}
              </span>
            }
            subtitle={cat.description}
          >
            {cat.keywords.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1">
                {cat.keywords.map((k) => (
                  <span key={k} className="rounded-md bg-white/5 px-1.5 py-0.5 text-[11px] text-zinc-400">
                    {k}
                  </span>
                ))}
              </div>
            )}
            <div className="divide-y divide-white/5">
              {cat.tools.map((t) => (
                <div key={t.name} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 font-mono text-[12.5px] text-zinc-200">
                      {t.name}
                      {t.confirm && (
                        <span title="Needs your spoken confirmation before it runs" className="text-amber-300">
                          <ShieldCheck className="size-3.5" />
                        </span>
                      )}
                    </div>
                    <div className="truncate text-[12px] text-zinc-500">{t.description}</div>
                  </div>
                  <Toggle
                    checked={t.enabled}
                    onChange={async (v) => {
                      await api.toggleTool(t.name, v);
                      void reload();
                    }}
                  />
                </div>
              ))}
              {cat.tools.length === 0 && <p className="py-2 text-[12px] text-zinc-500">Tools load when the server connects (press Test on the Connectors page).</p>}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
