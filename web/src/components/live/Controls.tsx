import clsx from "clsx";
import { Mic, MicOff, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import { useDevice } from "../../device/DeviceContext";

/** The push-to-talk orb. Its outer ring breathes with your mic level (CSS var --mic). */
export function MicOrb({
  holding,
  disabled,
  onDown,
  onUp,
}: {
  holding: boolean;
  disabled?: boolean;
  onDown: () => void;
  onUp: () => void;
}) {
  const { micLevelRef, state } = useDevice();
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      ref.current?.style.setProperty("--mic", Math.min(1, micLevelRef.current * 2.6).toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [micLevelRef]);
  const live = holding || state === "listening";

  return (
    <button
      ref={ref}
      onPointerDown={onDown}
      onPointerUp={onUp}
      onPointerLeave={onUp}
      disabled={disabled}
      title="Hold to talk (or hold Space)"
      className="group relative grid size-[92px] shrink-0 select-none place-items-center rounded-full outline-none transition-transform duration-200 active:scale-95 disabled:opacity-40"
    >
      {/* level ring */}
      <span
        className="absolute inset-0 rounded-full transition-[box-shadow] duration-75"
        style={{ boxShadow: live ? "0 0 0 calc(var(--mic, 0) * 22px) rgb(var(--state) / 0.14), 0 0 40px rgb(var(--state) / 0.35)" : "none" }}
      />
      {/* rotating sheen while live */}
      <span
        className={clsx(
          "absolute -inset-[2px] rounded-full opacity-0 transition-opacity",
          live && "animate-spin-slow opacity-100",
        )}
        style={{ background: "conic-gradient(from 0deg, transparent, rgb(var(--state)) 25%, transparent 50%)" }}
      />
      <span className="absolute inset-0 rounded-full bg-[radial-gradient(circle_at_32%_26%,#2b2e3a,#101117_62%,#07080b)] shadow-[inset_0_1px_0_rgba(255,255,255,0.1),inset_0_-8px_20px_rgba(0,0,0,0.6),0_22px_44px_-14px_rgba(0,0,0,0.9)] ring-1 ring-white/10" />
      <Mic className={clsx("relative size-7 transition-colors", live ? "text-[rgb(var(--state))]" : "text-zinc-200 group-hover:text-white")} />
    </button>
  );
}

export function ModeSwitch({ handsFree, onChange, disabled }: { handsFree: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className={clsx("relative grid grid-cols-2 rounded-xl border border-white/[0.07] bg-black/40 p-1", disabled && "opacity-40")}>
      <span
        className="absolute inset-y-1 w-[calc(50%-4px)] rounded-lg bg-white/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] transition-all duration-300"
        style={{ left: handsFree ? "calc(50% + 0px)" : "4px" }}
      />
      {[
        { on: false, label: "Push to talk" },
        { on: true, label: "Hands-free" },
      ].map((opt) => (
        <button
          key={opt.label}
          disabled={disabled}
          onClick={() => onChange(opt.on)}
          className={clsx(
            "relative px-3 py-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] transition-colors",
            handsFree === opt.on ? "text-zinc-100" : "text-zinc-500 hover:text-zinc-300",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function IconButton({
  title,
  onClick,
  disabled,
  active,
  danger,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "grid size-11 place-items-center rounded-xl border transition disabled:opacity-30",
        danger
          ? "border-rose-400/20 bg-rose-500/[0.06] text-rose-300 hover:bg-rose-500/15"
          : active
            ? "border-amber-300/30 bg-amber-400/10 text-amber-200"
            : "border-white/[0.07] bg-white/[0.03] text-zinc-300 hover:border-white/15 hover:bg-white/[0.06]",
      )}
    >
      {children}
    </button>
  );
}

export { Mic, MicOff, Square };
