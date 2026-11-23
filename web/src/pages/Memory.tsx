import { Check, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, Card, ErrorNote, Input, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { useLoad } from "../lib/hooks";

const when = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export function MemoryPage() {
  const { data, error, reload } = useLoad(api.memory, [], 5000);
  const [fact, setFact] = useState("");
  const del = async (kind: string, id: number) => {
    await api.deleteMemory(kind, id);
    void reload();
  };

  return (
    <>
      <PageHeader
        title="Memory"
        subtitle="What AIVA remembers about you, plus the notes, to-dos and reminders you dictated."
        actions={
          <Button onClick={async () => void (await api.resetConversation())} title="Forget the current conversation context (long-term facts stay)">
            <RotateCcw className="size-4" /> Reset conversation
          </Button>
        }
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Facts about you" subtitle="Injected into every conversation. Say “remember that…” or add here.">
          <form
            className="mb-3 flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!fact.trim()) return;
              await api.addFact(fact.trim());
              setFact("");
              void reload();
            }}
          >
            <Input placeholder="e.g. My teacher's name is Sharma sir" value={fact} onChange={(e) => setFact(e.target.value)} />
            <Button variant="primary" type="submit">
              <Plus className="size-4" />
            </Button>
          </form>
          <List items={data?.facts} empty="Nothing yet." render={(f) => f.text} onDelete={(f) => void del("facts", f.id)} />
        </Card>
        <Card title="Reminders & timers">
          <List
            items={data?.reminders}
            empty="No upcoming reminders."
            render={(r) => (
              <>
                <span className="text-zinc-200">{r.text}</span> <span className="text-zinc-500">· {r.kind} · {when(r.due_at)}</span>
              </>
            )}
            onDelete={(r) => void del("reminders", r.id)}
          />
        </Card>
        <Card title="To-do list">
          <List
            items={data?.todos}
            empty="All done!"
            render={(t) => <span className={t.done ? "text-zinc-500 line-through" : "text-zinc-200"}>{t.text}</span>}
            extra={(t) =>
              !t.done && (
                <Button
                  variant="ghost"
                  title="Mark done"
                  onClick={async () => {
                    await api.doneTodo(t.id);
                    void reload();
                  }}
                >
                  <Check className="size-4" />
                </Button>
              )
            }
            onDelete={(t) => void del("todos", t.id)}
          />
        </Card>
        <Card title="Notes">
          <List
            items={data?.notes}
            empty="No notes."
            render={(n) => (
              <>
                <span className="text-zinc-200">{n.text}</span> <span className="text-zinc-500">· {when(n.created_at)}</span>
              </>
            )}
            onDelete={(n) => void del("notes", n.id)}
          />
        </Card>
      </div>
    </>
  );
}

function List<T extends { id: number }>({
  items,
  empty,
  render,
  onDelete,
  extra,
}: {
  items?: T[];
  empty: string;
  render: (item: T) => React.ReactNode;
  onDelete: (item: T) => void;
  extra?: (item: T) => React.ReactNode;
}) {
  if (!items?.length) return <p className="text-[13px] text-zinc-500">{empty}</p>;
  return (
    <ul className="divide-y divide-white/5">
      {items.map((item) => (
        <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-[13px]">
          <div className="min-w-0">{render(item)}</div>
          <div className="flex shrink-0">
            {extra?.(item)}
            <Button variant="ghost" onClick={() => onDelete(item)} title="Delete">
              <Trash2 className="size-4" />
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
