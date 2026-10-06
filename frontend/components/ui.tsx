"use client";
import { ReactNode } from "react";
import { LEVEL_COLOR, LEVEL_NAME, confColor, pct } from "@/lib/format";

export function LevelBadge({ level, small }: { level: string; small?: boolean }) {
  const c = LEVEL_COLOR[level] || "#6b7a90";
  return (
    <span className={`inline-flex items-center gap-1 rounded font-bold  ${small ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-0.5 text-xs"}`} style={{ background: `${c}26`, color: c, border: `1px solid ${c}66` }}>
      {level}
      {!small && <span className="font-medium opacity-80">{(LEVEL_NAME[level] || "").charAt(0) + (LEVEL_NAME[level] || "").slice(1).toLowerCase()}</span>}
    </span>
  );
}

export function ConfBadge({ value, label }: { value?: number; label?: string }) {
  const c = confColor(label);
  return (
    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold" style={{ background: `${c}22`, color: c, border: `1px solid ${c}55` }}>
      {value !== undefined && pct(value)} {label}
    </span>
  );
}

export function DemoBadge({ className = "" }: { className?: string }) {
  return <span className={`rounded border border-warn/40 bg-warn/10 px-1.5 py-0.5 text-[11px] font-semibold text-warn ${className}`}>DEMONSTRATION DATA</span>;
}

export function RealBadge({ className = "" }: { className?: string }) {
  return <span className={`rounded border border-ok/50 bg-ok/10 px-1.5 py-0.5 text-[11px] font-bold  text-ok ${className}`}>REAL DATA</span>;
}

export function EstimateBadge() {
  return <span className="rounded border border-accent/50 bg-accent/10 px-1.5 py-0.5 text-[11px] font-bold  text-accent">ESTIMATE</span>;
}

export function Panel({ title, right, children, className = "", pad = true }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
          <h3 className="text-sm font-semibold text-strong">{title}</h3>
          <div className="flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className={pad ? "p-3.5" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, color, big }: { label: string; value: ReactNode; sub?: ReactNode; color?: string; big?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[11px] font-semibold   text-muted">{label}</div>
      <div className={`tabular-nums font-bold leading-tight ${big ? "text-3xl" : "text-xl"}`} style={{ color: color || "#0b1b33" }}>
        {value}
      </div>
      {sub && <div className="truncate text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

export function Bar({ value, color = "#3b9eff", label, right }: { value: number; color?: string; label?: string; right?: ReactNode }) {
  return (
    <div>
      {(label || right) && (
        <div className="mb-0.5 flex justify-between text-xs">
          <span className="text-muted">{label}</span>
          <span className="tabular-nums text-text">{right ?? pct(value)}</span>
        </div>
      )}
      <div className="h-1.5 w-full overflow-hidden rounded bg-ink">
        <div className="h-full rounded" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }} />
      </div>
    </div>
  );
}

export function Spinner({ text }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-xs text-muted">
      <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-accent" /> {text || "Loading..."}
    </div>
  );
}

export function ErrorBox({ error }: { error?: string | null }) {
  if (!error) return null;
  return <div className="rounded border border-p1/50 bg-p1/10 px-3 py-2 text-xs text-p1">{error}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded border border-dashed border-line p-6 text-center text-xs text-muted">{children}</div>;
}

export function Toggle({ on, onChange, label, color }: { on: boolean; onChange: (v: boolean) => void; label: string; color?: string }) {
  return (
    <button onClick={() => onChange(!on)} className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-panel2">
      <span className={`flex h-3.5 w-3.5 items-center justify-center rounded-sm border ${on ? "border-transparent" : "border-line"}`} style={{ background: on ? color || "#3b9eff" : "transparent" }}>
        {on && <span className="text-[11px] font-bold leading-none text-ink">✓</span>}
      </span>
      <span className={on ? "text-text" : "text-muted"}>{label}</span>
    </button>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-0.5 border-b border-line">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} className={`px-3 py-1.5 text-xs font-semibold   ${value === t.key ? "border-b-2 border-accent text-strong" : "text-muted hover:text-text"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Provenance({ items }: { items: string[] }) {
  return <div className="mt-1 text-[11px] text-muted">Sources: {items.join(" · ")}</div>;
}

export function PageHeader({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-lg font-bold  text-strong">{title}</h1>
        {sub && <div className="text-xs text-muted">{sub}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{right}</div>
    </div>
  );
}
