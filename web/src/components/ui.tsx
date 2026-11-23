import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Card({ title, subtitle, actions, children, className }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-2xl border border-white/8 bg-white/[0.03] p-5 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] backdrop-blur", className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-[15px] font-semibold tracking-tight text-zinc-100">{title}</h2>}
            {subtitle && <p className="mt-1 text-[13px] leading-relaxed text-zinc-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

type Variant = "primary" | "ghost" | "danger" | "subtle";

export function Button({ variant = "subtle", busy, className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-[13px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-gradient-to-r from-cyan-400 to-violet-500 text-zinc-950 hover:brightness-110",
        variant === "subtle" && "border border-white/10 bg-white/5 text-zinc-200 hover:bg-white/10",
        variant === "ghost" && "text-zinc-300 hover:bg-white/5",
        variant === "danger" && "border border-rose-500/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20",
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
        "w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-[13px] text-zinc-100 placeholder:text-zinc-500 outline-none transition focus:border-cyan-400/60 focus:ring-2 focus:ring-cyan-400/20",
        props.className,
      )}
    />
  );
}

export function Badge({ tone = "zinc", children }: { tone?: "zinc" | "green" | "amber" | "rose" | "cyan" | "violet"; children: ReactNode }) {
  const tones = {
    zinc: "bg-zinc-500/15 text-zinc-300 ring-zinc-400/20",
    green: "bg-emerald-500/15 text-emerald-300 ring-emerald-400/25",
    amber: "bg-amber-500/15 text-amber-300 ring-amber-400/25",
    rose: "bg-rose-500/15 text-rose-300 ring-rose-400/25",
    cyan: "bg-cyan-500/15 text-cyan-300 ring-cyan-400/25",
    violet: "bg-violet-500/15 text-violet-300 ring-violet-400/25",
  };
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", tones[tone])}>{children}</span>;
}

export function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx("relative h-5 w-9 shrink-0 rounded-full transition disabled:opacity-40", checked ? "bg-cyan-400" : "bg-white/15")}
    >
      <span className={clsx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
    </button>
  );
}

/** Horizontal quota/usage meter. */
export function Meter({ value, label, hint }: { value: number | null; label?: string; hint?: string }) {
  const v = value == null ? null : Math.max(0, Math.min(1, value));
  const color = v == null ? "bg-zinc-600" : v > 0.5 ? "bg-emerald-400" : v > 0.2 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div>
      {(label || hint) && (
        <div className="mb-1 flex justify-between text-[11px] text-zinc-400">
          <span>{label}</span>
          <span>{hint}</span>
        </div>
      )}
      <div className="h-1.5 overflow-hidden rounded-full bg-white/8">
        <div className={clsx("h-full rounded-full transition-all duration-500", color)} style={{ width: v == null ? "100%" : `${v * 100}%`, opacity: v == null ? 0.25 : 1 }} />
      </div>
    </div>
  );
}

export function StatusDot({ status }: { status: "ok" | "warn" | "fail" | "idle" }) {
  const map = { ok: "bg-emerald-400", warn: "bg-amber-400", fail: "bg-rose-500", idle: "bg-zinc-500" };
  return <span className={clsx("inline-block size-2 rounded-full", map[status], status === "ok" && "shadow-[0_0_10px] shadow-emerald-400/60")} />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-zinc-400">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-[13px] text-rose-200">{children}</p>;
}
