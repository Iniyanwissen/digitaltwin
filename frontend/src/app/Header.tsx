import { useHealth } from "@/api/hooks";
import { HealthIndicator } from "@/components/HealthIndicator";

import type { NavSection } from "./navigation";

export function Header({ section }: { section: NavSection | undefined }) {
  const { data } = useHealth();
  const runStatus = data?.components.simulation_engine?.info.run_status;

  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <div>
        <h1 className="text-lg font-semibold">{section?.label ?? "Not found"}</h1>
        {section && <p className="text-sm text-slate-500">{section.description}</p>}
      </div>
      <div className="flex items-center gap-3">
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
          Simulation: {typeof runStatus === "string" ? runStatus.replace("_", " ").toLowerCase() : "—"}
        </span>
        <HealthIndicator />
      </div>
    </header>
  );
}
