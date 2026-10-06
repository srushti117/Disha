"use client";
export type Step = { key: string; label: string; status: string; detail?: string };

const ICON: Record<string, { sym: string; cls: string }> = {
  done: { sym: "✓", cls: "text-ok" },
  running: { sym: "●", cls: "text-accent pulse-dot" },
  awaiting: { sym: "○", cls: "text-warn" },
  pending: { sym: "·", cls: "text-muted" },
};

export default function Pipeline({ steps, compact }: { steps: Step[]; compact?: boolean }) {
  return (
    <ol className={compact ? "grid grid-cols-2 gap-x-4 gap-y-1 md:grid-cols-5" : "space-y-1"}>
      {steps.map((s, i) => {
        const ic = ICON[s.status] || ICON.pending;
        return (
          <li key={s.key} className="flex items-start gap-2 text-[13px]" title={s.detail || ""}>
            <span className={`w-4 text-center font-bold ${ic.cls}`}>{ic.sym}</span>
            <span className="w-4 tabular-nums text-xs text-muted">{i + 1}</span>
            <span className={`w-20 shrink-0 font-medium ${s.status === "pending" ? "text-muted" : "text-strong"}`}>{s.label || s.key}</span>
            {!compact && <span className="min-w-0 flex-1 truncate text-xs text-muted">{s.detail}</span>}
          </li>
        );
      })}
    </ol>
  );
}
