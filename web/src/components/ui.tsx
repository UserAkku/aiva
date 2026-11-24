import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  hud,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  hud?: boolean;
}) {
  return (
    <section className={clsx("glass rounded-2xl p-5", hud && "hud", className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-[14.5px] font-medium tracking-tight text-zinc-100">{title}</h2>}
            {subtitle && <p className="mt-1 text-[13px] leading-relaxed text-zinc-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

type Variant = "primary" | "ghost" | "danger" | "subtle";

export function Button({
  variant = "subtle",
  busy,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-[13px] font-medium transition duration-200 disabled:cursor-not-allowed disabled:opacity-40",
        variant === "primary" &&
          "bg-zinc-100 text-zinc-950 shadow-[0_0_0_1px_rgba(255,255,255,0.6),0_8px_24px_-8px_rgba(255,255,255,0.35)] hover:bg-white",
        variant === "subtle" && "border border-white/[0.08] bg-white/[0.04] text-zinc-200 hover:border-white/15 hover:bg-white/[0.07]",
        variant === "ghost" && "text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100",
        variant === "danger" && "border border-rose-400/20 bg-rose-500/[0.08] text-rose-200 hover:bg-rose-500/15",
        className,
      )}
    >
      {busy && <Loader2 className="size-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-xl border border-white/[0.08] bg-black/40 px-3 py-2 text-[13px] text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-cyan-300/40 focus:ring-4 focus:ring-cyan-300/10",
        props.className,
      )}
    />
  );
}

export function Badge({ tone = "zinc", children }: { tone?: "zinc" | "green" | "amber" | "rose" | "cyan" | "violet"; children: ReactNode }) {
  const tones = {
    zinc: "text-zinc-400 border-zinc-500/25 bg-zinc-500/[0.07]",
    green: "text-emerald-300 border-emerald-400/25 bg-emerald-400/[0.07]",
    amber: "text-amber-300 border-amber-400/25 bg-amber-400/[0.07]",
    rose: "text-rose-300 border-rose-400/25 bg-rose-400/[0.07]",
    cyan: "text-cyan-300 border-cyan-400/25 bg-cyan-400/[0.07]",
    violet: "text-violet-300 border-violet-400/25 bg-violet-400/[0.07]",
  };
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] uppercase tracking-wider", tones[tone])}>
      {children}
    </span>
  );
}

export function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative h-5 w-9 shrink-0 rounded-full border transition disabled:opacity-40",
        checked ? "border-cyan-300/50 bg-cyan-400/80 shadow-[0_0_14px_rgba(34,211,238,0.45)]" : "border-white/10 bg-white/[0.06]",
      )}
    >
      <span className={clsx("absolute top-[2px] size-3.5 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-[2px]")} />
    </button>
  );
}

/** Horizontal quota/usage meter. */
export function Meter({ value, label, hint }: { value: number | null; label?: string; hint?: string }) {
  const v = value == null ? null : Math.max(0, Math.min(1, value));
  const color = v == null ? "bg-zinc-600" : v > 0.5 ? "bg-emerald-400" : v > 0.2 ? "bg-amber-400" : "bg-rose-400";
  const glow = v == null ? "" : v > 0.5 ? "shadow-[0_0_10px_rgba(52,211,153,0.6)]" : v > 0.2 ? "shadow-[0_0_10px_rgba(251,191,36,0.5)]" : "shadow-[0_0_10px_rgba(251,113,133,0.6)]";
  return (
    <div>
      {(label || hint) && (
        <div className="mb-1.5 flex justify-between font-mono text-[10.5px] uppercase tracking-wider text-zinc-500">
          <span>{label}</span>
          <span>{hint}</span>
        </div>
      )}
      <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className={clsx("h-full rounded-full transition-all duration-500", color, glow)}
          style={{ width: v == null ? "100%" : `${v * 100}%`, opacity: v == null ? 0.2 : 1 }}
        />
      </div>
    </div>
  );
}

export function StatusDot({ status }: { status: "ok" | "warn" | "fail" | "idle" }) {
  const map = {
    ok: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]",
    warn: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]",
    fail: "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]",
    idle: "bg-zinc-500",
  };
  return <span className={clsx("inline-block size-1.5 rounded-full", map[status])} />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-white">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-zinc-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-rose-400/20 bg-rose-500/[0.07] px-3 py-2 text-[13px] text-rose-200">{children}</p>;
}
