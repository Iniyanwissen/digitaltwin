import { Construction } from "lucide-react";

import type { NavTab } from "@/app/navigation";

export function PlaceholderPanel({ tab }: { tab: NavTab }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8">
      <div className="flex items-center gap-3 text-slate-500">
        <Construction className="h-5 w-5" />
        <span className="text-sm font-medium">Arrives in Phase {tab.phase}</span>
      </div>
      <ul className="mt-4 list-disc space-y-1 pl-6 text-sm text-slate-600">
        {tab.features.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>
    </div>
  );
}
