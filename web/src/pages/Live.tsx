import clsx from "clsx";
import { Bot, Mic, MicOff, Send, Sparkles, Square, Trash2, User, Wrench, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { FaceCanvas, type OledColor } from "../components/FaceCanvas";
import { Badge, Button, Card, Meter, Toggle } from "../components/ui";
import { useDevice } from "../device/DeviceContext";
import { ANIMATIONS, EMOTIONS, type Animation } from "../face/presets";
import type { Status } from "../lib/api";

const STATE_LABEL: Record<string, { text: string; tone: "zinc" | "green" | "amber" | "cyan" | "violet" | "rose" }> = {
  offline: { text: "Offline — reconnecting…", tone: "rose" },
  connecting: { text: "Connecting…", tone: "amber" },
  idle: { text: "Idle", tone: "zinc" },
  listening: { text: "Listening", tone: "green" },
  thinking: { text: "Thinking", tone: "violet" },
  speaking: { text: "Speaking", tone: "cyan" },
};

const SAMPLES = [
  "Hi AIVA! Apna introduction do",
  "1 से 20 तक गिनती करो",
  "आज Delhi का weather कैसा है?",
  "Ek joke sunao",
  "YouTube pe lofi music chalao",
  "Make a PDF on the solar system for class 6",
  "Mera inbox check karo",
  "Dance karke dikhao!",
];

export function LivePage({ status }: { status: Status | null }) {
  const { client, engine, state, captions, micLevel, clearCaptions } = useDevice();
  const [text, setText] = useState("");
  const [handsFree, setHandsFree] = useState(client.handsFree);
  const [holding, setHolding] = useState(false);
  const [muted, setMuted] = useState(false);
  const [color, setColor] = useState<OledColor>((localStorage.getItem("aiva.oled") as OledColor) || "cyan");
  const [micError, setMicError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [captions]);

  useEffect(() => localStorage.setItem("aiva.oled", color), [color]);

  // Space bar = push-to-talk (when not typing)
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || (e.target as HTMLElement).tagName === "INPUT") return;
      e.preventDefault();
      void startTalk();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || (e.target as HTMLElement).tagName === "INPUT") return;
      e.preventDefault();
      void stopTalk();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  });

  const startTalk = async () => {
    try {
      setHolding(true);
      setMicError(null);
      await client.pushToTalk(true);
    } catch (e) {
      setHolding(false);
      setMicError(e instanceof Error ? e.message : String(e));
    }
  };
  const stopTalk = async () => {
    if (!holding) return;
    setHolding(false);
    await client.pushToTalk(false);
  };

  const toggleHandsFree = async (on: boolean) => {
    try {
      setMicError(null);
      await client.setHandsFree(on);
      setHandsFree(on);
    } catch (e) {
      setMicError(e instanceof Error ? e.message : String(e));
    }
  };

  const send = async (value = text) => {
    const v = value.trim();
    if (!v) return;
    setText("");
    await client.sendText(v);
  };

  const label = STATE_LABEL[state] ?? STATE_LABEL.idle;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      {/* ── the virtual device ─────────────────────────────────────── */}
      <div className="space-y-5">
        <div className="bezel relative rounded-[28px] p-5">
          <div className="absolute left-4 top-4 size-1.5 rounded-full bg-white/10" />
          <div className="absolute right-4 top-4 size-1.5 rounded-full bg-white/10" />
          <div className="absolute bottom-4 left-4 size-1.5 rounded-full bg-white/10" />
          <div className="absolute bottom-4 right-4 size-1.5 rounded-full bg-white/10" />
          <div className="rounded-2xl border border-black bg-black p-3 shadow-inner">
            <FaceCanvas engine={engine} color={color} className="aspect-[2/1] w-full" />
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 px-1">
            <div className="flex items-center gap-2">
              <Badge tone={label.tone}>{label.text}</Badge>
              <span className="text-[11px] text-zinc-500">SSD1306 · 128×64 · ESP32-S3 simulator</span>
            </div>
            <div className="flex items-center gap-1.5">
              {(["cyan", "white", "blue", "green", "bicolor"] as OledColor[]).map((c) => (
                <button
                  key={c}
                  title={c}
                  onClick={() => setColor(c)}
                  className={clsx(
                    "size-4 rounded-full ring-2 ring-offset-2 ring-offset-zinc-900 transition",
                    color === c ? "ring-white/70" : "ring-transparent",
                    c === "cyan" && "bg-cyan-300",
                    c === "white" && "bg-slate-100",
                    c === "blue" && "bg-sky-400",
                    c === "green" && "bg-emerald-300",
                    c === "bicolor" && "bg-gradient-to-b from-yellow-300 from-40% to-sky-400 to-40%",
                  )}
                />
              ))}
            </div>
          </div>
        </div>

        <Card>
          <div className="flex flex-wrap items-center gap-5">
            <button
              onPointerDown={() => void startTalk()}
              onPointerUp={() => void stopTalk()}
              onPointerLeave={() => void stopTalk()}
              disabled={state === "offline"}
              className={clsx(
                "grid size-20 shrink-0 place-items-center rounded-full text-zinc-950 transition select-none disabled:opacity-40",
                holding ? "scale-95 bg-cyan-300 pulse-ring" : "bg-gradient-to-br from-cyan-400 to-violet-500 hover:brightness-110",
              )}
              title="Hold to talk (or hold Space)"
            >
              <Mic className="size-8" />
            </button>
            <div className="min-w-48 flex-1 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[13px] font-medium text-zinc-200">Hands-free mode</div>
                  <div className="text-[12px] text-zinc-500">Talk anytime; interrupt AIVA by speaking.</div>
                </div>
                <Toggle checked={handsFree} onChange={(v) => void toggleHandsFree(v)} disabled={state === "offline"} />
              </div>
              <Meter value={Math.min(1, micLevel * 2.5)} label="Mic level" hint={muted ? "muted" : holding ? "push-to-talk" : handsFree ? "listening" : "off"} />
            </div>
            <div className="flex flex-col gap-2">
              <Button
                variant="subtle"
                onClick={() => {
                  client.muted = !muted;
                  setMuted(!muted);
                }}
              >
                {muted ? <MicOff className="size-4" /> : <Mic className="size-4" />} {muted ? "Unmute" : "Mute"}
              </Button>
              <Button variant="danger" onClick={() => client.abort()} disabled={state !== "speaking" && state !== "thinking"}>
                <Square className="size-3.5" /> Stop
              </Button>
            </div>
          </div>
          {micError && <p className="mt-3 text-[12px] text-rose-300">Microphone: {micError}. Allow mic access in the browser.</p>}
          {!status?.llm_ready && status && (
            <p className="mt-3 flex items-center gap-2 rounded-xl bg-amber-500/10 px-3 py-2 text-[12.5px] text-amber-200">
              <TriangleAlert className="size-4" /> No AI provider key yet — add a free Groq key on the{" "}
              <a className="underline" href="#/connectors">Connectors</a> page.
            </p>
          )}
        </Card>

        <Card title="Face lab" subtitle="Preview every emotion and animation exactly as the ESP32 OLED will show it.">
          <div className="flex flex-wrap gap-1.5">
            {EMOTIONS.map((e) => (
              <button key={e} onClick={() => engine.setEmotion(e, 4000)} className="rounded-lg bg-white/5 px-2.5 py-1 text-[12px] text-zinc-300 hover:bg-white/10">
                {e}
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {ANIMATIONS.map((a) => (
              <button key={a} onClick={() => engine.play(a as Animation)} className="rounded-lg bg-violet-500/10 px-2.5 py-1 text-[12px] text-violet-200 hover:bg-violet-500/20">
                ▶ {a}
              </button>
            ))}
          </div>
        </Card>
      </div>

      {/* ── conversation ──────────────────────────────────────────── */}
      <Card
        className="flex h-[calc(100vh-56px)] min-h-[560px] flex-col xl:sticky xl:top-7"
        title="Conversation"
        subtitle="Live captions of what you said and what AIVA says."
        actions={
          <Button variant="ghost" onClick={clearCaptions} title="Clear captions">
            <Trash2 className="size-4" />
          </Button>
        }
      >
        <div ref={listRef} className="-mx-2 flex-1 space-y-3 overflow-y-auto px-2 pb-2">
          {captions.length === 0 && (
            <div className="mt-6 text-center text-[13px] text-zinc-500">
              <Sparkles className="mx-auto mb-2 size-5 text-cyan-300" />
              Hold the mic (or Space) and talk — or try one of these:
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SAMPLES.map((s) => (
                  <button key={s} onClick={() => void send(s)} className="rounded-full border border-white/10 px-3 py-1 text-[12px] text-zinc-300 hover:bg-white/5">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {captions.map((c) =>
            c.role === "tool" ? (
              <div key={c.id} className="flex items-center gap-2 pl-10 text-[12px] text-amber-200/80">
                <Wrench className="size-3.5" /> using <code className="rounded bg-amber-500/10 px-1.5 py-0.5">{c.text}</code>
              </div>
            ) : c.role === "notice" ? (
              <div key={c.id} className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-[12.5px] text-amber-100">
                ⚠ {c.text}
              </div>
            ) : (
              <div key={c.id} className={clsx("flex gap-2.5", c.role === "user" && "flex-row-reverse")}>
                <div className={clsx("grid size-8 shrink-0 place-items-center rounded-full", c.role === "user" ? "bg-white/10" : "bg-gradient-to-br from-cyan-400 to-violet-500 text-zinc-950")}>
                  {c.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
                </div>
                <div
                  className={clsx(
                    "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[14px] leading-relaxed",
                    c.role === "user" ? "rounded-tr-sm bg-cyan-500/15 text-cyan-50" : "rounded-tl-sm bg-white/[0.06] text-zinc-100",
                  )}
                >
                  {c.text}
                </div>
              </div>
            ),
          )}
          {state === "thinking" && (
            <div className="flex items-center gap-2 pl-10 text-[12px] text-violet-300">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="size-1.5 animate-bounce rounded-full bg-violet-300" style={{ animationDelay: `${i * 120}ms` }} />
                ))}
              </span>
              thinking…
            </div>
          )}
        </div>
        <form
          className="mt-3 flex gap-2 border-t border-white/6 pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type to AIVA… (Hinglish works!)"
            className="flex-1 rounded-xl border border-white/10 bg-black/30 px-3.5 py-2.5 text-[14px] text-zinc-100 outline-none placeholder:text-zinc-500 focus:border-cyan-400/50"
          />
          <Button variant="primary" type="submit" disabled={!text.trim() || state === "offline"}>
            <Send className="size-4" />
          </Button>
        </form>
      </Card>
    </div>
  );
}
