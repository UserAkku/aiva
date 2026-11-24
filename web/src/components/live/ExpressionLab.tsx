import clsx from "clsx";
import { ChevronDown, Palette } from "lucide-react";
import { useState } from "react";
import { useDevice } from "../../device/DeviceContext";
import { ANIMATIONS, type Animation, EMOTIONS } from "../../face/presets";
import type { OledColor } from "../FaceCanvas";

const COLORS: Array<{ id: OledColor; swatch: string }> = [
  { id: "cyan", swatch: "bg-cyan-300" },
  { id: "white", swatch: "bg-slate-100" },
  { id: "blue", swatch: "bg-sky-400" },
  { id: "green", swatch: "bg-emerald-300" },
  { id: "bicolor", swatch: "bg-[linear-gradient(180deg,#fde047_40%,#38bdf8_40%)]" },
];

/** Collapsible playground for every emotion/animation and the OLED tint. */
export function ExpressionLab({ color, onColor }: { color: OledColor; onColor: (c: OledColor) => void }) {
  const { engine } = useDevice();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [mouth, setMouth] = useState(engine.showMouth);

  return (
    <section className="glass rounded-2xl">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-5 py-3.5">
        <span className="flex items-center gap-3">
          <Palette className="size-4 text-zinc-500" />
          <span className="label !text-zinc-400">Expression lab</span>
          <span className="font-mono text-[10.5px] text-zinc-600">
            {EMOTIONS.length} emotions · {ANIMATIONS.length} animations
          </span>
        </span>
        <ChevronDown className={clsx("size-4 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t border-white/[0.05] px-5 pb-5 pt-4">
          <div className="flex flex-wrap gap-1.5">
            {EMOTIONS.map((e) => (
              <button
                key={e}
                onClick={() => {
                  engine.setEmotion(e, 4000);
                  setActive(e);
                }}
                className={clsx(
                  "rounded-lg border px-2.5 py-1 font-mono text-[11px] lowercase transition",
                  active === e
                    ? "border-[rgb(var(--state)/0.5)] bg-[rgb(var(--state)/0.1)] text-zinc-100"
                    : "border-white/[0.07] bg-white/[0.02] text-zinc-400 hover:border-white/15 hover:text-zinc-200",
                )}
              >
                {e}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {ANIMATIONS.map((a) => (
              <button
                key={a}
                onClick={() => engine.play(a as Animation)}
                className="rounded-lg border border-violet-300/15 bg-violet-400/[0.05] px-2.5 py-1 font-mono text-[11px] text-violet-200/90 transition hover:bg-violet-400/[0.12]"
              >
                ▶ {a.replace("_", " ")}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="label">Style</span>
            {[
              { on: true, label: "Eyes + mouth" },
              { on: false, label: "Cozmo eyes" },
            ].map((o) => (
              <button
                key={o.label}
                onClick={() => {
                  engine.showMouth = o.on;
                  setMouth(o.on);
                }}
                className={clsx(
                  "rounded-lg border px-2.5 py-1 font-mono text-[11px] transition",
                  mouth === o.on ? "border-[rgb(var(--state)/0.5)] bg-[rgb(var(--state)/0.1)] text-zinc-100" : "border-white/[0.07] text-zinc-500 hover:text-zinc-200",
                )}
              >
                {o.label}
              </button>
            ))}
            <span className="label ml-3">OLED tint</span>
            {COLORS.map((c) => (
              <button
                key={c.id}
                title={c.id}
                onClick={() => onColor(c.id)}
                className={clsx(
                  "size-4 rounded-full ring-2 ring-offset-2 ring-offset-[#0b0c10] transition",
                  c.swatch,
                  color === c.id ? "ring-white/60" : "ring-transparent hover:ring-white/20",
                )}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
