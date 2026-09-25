import { useState } from "react";

import { useHealth } from "@/api/hooks";
import type { ComponentStatus } from "@/api/types";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<ComponentStatus | "unknown", { dot: string; label: string }> = {
  ok: { dot: "bg-emerald-500", label: "Healthy" },
  degraded: { dot: "bg-amber-500", label: "Degraded" },
  down: { dot: "bg-red-500", label: "Down" },
  unknown: { dot: "bg-slate-400", label: "Checking…" },
};

function labelFor(name: string): string {
  return name.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function HealthIndicator() {
  const { data, isError, isPending } = useHealth();
  const [open, setOpen] = useState(false);

  const key: ComponentStatus | "unknown" = isError ? "down" : isPending ? "unknown" : data.status;
  const style = STATUS_STYLE[key];
  const text = isError ? "API unreachable" : style.label;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
        aria-expanded={open}
      >
        <span className={cn("h-2.5 w-2.5 rounded-full", style.dot)} data-testid="health-dot" />
        {text}
      </button>
      {open && data && (
        <div className="absolute right-0 z-10 mt-2 w-80 rounded-lg border border-slate-200 bg-white p-3 shadow-lg">
          <ul className="space-y-2">
            {Object.entries(data.components).map(([name, component]) => (
              <li key={name} className="flex items-start gap-2 text-sm">
                <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", STATUS_STYLE[component.status].dot)} />
                <div>
                  <div className="font-medium text-slate-800">{labelFor(name)}</div>
                  <div className="text-xs text-slate-500">{component.detail}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
