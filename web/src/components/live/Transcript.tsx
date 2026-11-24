import clsx from "clsx";
import { Check, CornerDownLeft, Loader2, Sparkles, Trash2, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Caption } from "../../device/DeviceClient";
import { useDevice } from "../../device/DeviceContext";

const SUGGESTIONS = [
  "Hi AIVA! Apna introduction do",
  "1 से 20 तक गिनती करो",
  "आज Delhi का AQI कितना है?",
  "Ek mazedaar joke sunao",
  "Make a PDF on the solar system for class 6",
  "Dance karke dikhao!",
];

const time = (ts: number) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function Entry({ c }: { c: Caption }) {
  if (c.role === "tool") {
    return (
      <div className="rise flex items-center gap-2 pl-1 font-mono text-[11px] text-zinc-500">
        <span
          className={clsx(
            "grid size-4 place-items-center rounded-full border",
            c.status === "running" && "border-violet-400/40 text-violet-300",
            c.status === "done" && "border-emerald-400/40 text-emerald-300",
            c.status === "failed" && "border-rose-400/40 text-rose-300",
          )}
        >
          {c.status === "running" ? <Loader2 className="size-2.5 animate-spin" /> : c.status === "failed" ? <X className="size-2.5" /> : <Check className="size-2.5" />}
        </span>
        <span className="uppercase tracking-[0.12em]">{c.status === "running" ? "running" : c.status === "failed" ? "failed" : "used"}</span>
        <span className="rounded-md border border-white/[0.07] bg-white/[0.03] px-1.5 py-0.5 text-zinc-300">{c.text}</span>
      </div>
    );
  }
  if (c.role === "notice") {
    return (
      <div className="rise flex gap-2 rounded-xl border border-amber-300/20 bg-amber-400/[0.06] px-3 py-2 text-[13px] text-amber-100">
        <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-300" /> {c.text}
      </div>
    );
  }
  const you = c.role === "user";
  return (
    <div className={clsx("rise flex flex-col gap-1.5", you && "items-end")}>
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-zinc-600">
        {!you && <span className="size-1.5 rounded-full bg-[rgb(var(--state))] shadow-[0_0_8px_rgb(var(--state))]" />}
        <span className={you ? "" : "text-zinc-400"}>{you ? "You" : "AIVA"}</span>
        <span>{time(c.ts)}</span>
      </div>
      {you ? (
        <div className="max-w-[88%] rounded-2xl rounded-tr-md border border-white/[0.07] bg-white/[0.045] px-3.5 py-2.5 text-[14.5px] leading-relaxed text-zinc-100">
          {c.text}
        </div>
      ) : (
        <div className="max-w-[94%] border-l border-[rgb(var(--state)/0.5)] pl-3.5 text-[15px] leading-[1.7] text-zinc-100">{c.text}</div>
      )}
    </div>
  );
}

export function Transcript({ onSend }: { onSend: (text: string) => void }) {
  const { captions, state, clearCaptions } = useDevice();
  const [text, setText] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [captions, state]);

  const submit = (value: string) => {
    const v = value.trim();
    if (!v) return;
    setText("");
    onSend(v);
  };

  return (
    <section className="glass hud flex h-full min-h-[560px] flex-col rounded-3xl">
      <header className="flex items-center justify-between border-b border-white/[0.05] px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="label !text-zinc-400">Transcript</span>
          <span className="font-mono text-[10.5px] text-zinc-600">{captions.filter((c) => c.role === "user").length} turns</span>
        </div>
        <button onClick={clearCaptions} title="Clear" className="rounded-lg p-1.5 text-zinc-600 transition hover:bg-white/5 hover:text-zinc-300">
          <Trash2 className="size-4" />
        </button>
      </header>

      <div ref={listRef} className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {captions.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="grid size-11 place-items-center rounded-2xl border border-white/[0.08] bg-white/[0.03]">
              <Sparkles className="size-4.5 text-[rgb(var(--state))]" />
            </div>
            <p className="mt-4 text-[15px] font-medium text-zinc-200">Talk to AIVA</p>
            <p className="mt-1 text-[13px] text-zinc-500">Hold the orb or Space — or try one of these:</p>
            <div className="mt-5 flex max-w-sm flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => submit(s)}
                  className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[12.5px] text-zinc-400 transition hover:border-[rgb(var(--state)/0.4)] hover:text-zinc-100"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {captions.map((c) => (
          <Entry key={c.id} c={c} />
        ))}
        {state === "thinking" && (
          <div className="rise flex items-center gap-2.5 pl-1">
            <span className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span key={i} className="size-1.5 animate-bounce rounded-full bg-[rgb(var(--state))]" style={{ animationDelay: `${i * 140}ms` }} />
              ))}
            </span>
            <span className="shimmer-text font-mono text-[11px] uppercase tracking-[0.2em]">AIVA is thinking</span>
          </div>
        )}
      </div>

      <form
        className="border-t border-white/[0.05] p-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
      >
        <div className="group relative">
          <div className="absolute -inset-px rounded-2xl bg-[linear-gradient(90deg,rgb(var(--state)/0.5),transparent_40%,transparent_60%,rgb(var(--state)/0.5))] opacity-0 blur-[2px] transition-opacity duration-300 group-focus-within:opacity-100" />
          <div className="relative flex items-center gap-3 rounded-2xl border border-white/[0.08] bg-[#07080c] px-4 py-3">
            <Sparkles className="size-4 shrink-0 text-zinc-600" />
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask AIVA anything — Hinglish works"
              className="min-w-0 flex-1 bg-transparent text-[14.5px] text-zinc-100 outline-none placeholder:text-zinc-600"
            />
            <button
              type="submit"
              disabled={!text.trim() || state === "offline"}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.06] px-2 py-1 font-mono text-[10.5px] uppercase tracking-wider text-zinc-300 transition enabled:hover:bg-white/10 disabled:opacity-30"
            >
              send <CornerDownLeft className="size-3" />
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
