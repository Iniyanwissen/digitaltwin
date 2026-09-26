import { useState } from "react";

import { cn } from "@/lib/utils";

import type { View } from "./floorRenderer";
import type { LiveStore } from "./store";
import type { ActivityItem, PersonStatus } from "./types";
import { useLiveRevision } from "./useLive";

const MAX_LINES = 120;
const MAX_MATCHES = 4;

function matches(q: string, code: string, name: string, person: string): boolean {
  return code.toLowerCase() === q || person.toLowerCase() === q || name.toLowerCase().includes(q);
}

function Chip({ code, colour }: { code: string; colour: string | undefined }) {
  return (
    <span className="rounded px-1 font-semibold text-twin-bg" style={{ background: colour ?? "#94a3b8" }}>
      {code}
    </span>
  );
}

/**
 * Who is doing what. Operational View: only what badge readers, workstations and room panels
 * report. Simulation View: ground truth (labelled). Search by short code (E283) or name.
 */
export function PeoplePanel({
  store,
  view,
  deptColor,
}: {
  store: LiveStore;
  view: View;
  deptColor: Record<string, string>;
}) {
  useLiveRevision(store);
  const [query, setQuery] = useState("");
  const truth = view === "simulation";
  const people: Record<string, PersonStatus> = truth ? store.truthPeople : store.people;
  const activity: ActivityItem[] = truth ? store.truthActivity : store.activity;
  const q = query.trim().toLowerCase();
  const found = q
    ? Object.entries(people)
        .filter(([id, p]) => matches(q, p.code, p.name, id))
        .slice(0, MAX_MATCHES)
    : [];
  const lines = (q ? activity.filter((a) => matches(q, a.code, a.name, a.person)) : activity).slice(0, MAX_LINES);

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-twin-line bg-twin-panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold tracking-wider text-twin-muted uppercase">People activity</h2>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px]",
            truth ? "border border-dashed border-twin-anonymous text-twin-anonymous" : "bg-twin-line text-twin-muted",
          )}
          title={truth ? "Ground truth from the simulation" : "Only identified events: badges, logins, room panels"}
        >
          {truth ? "simulation truth" : "observed"}
        </span>
      </div>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Follow someone: E283 or a name"
        className="mb-2 rounded-md border border-twin-line bg-twin-inset px-2 py-1 text-sm text-twin-text placeholder:text-twin-muted"
      />
      {found.map(([id, p]) => (
        <div key={id} className="mb-2 rounded-lg border border-twin-line bg-twin-inset p-2 text-xs">
          <div className="flex items-center gap-2">
            <Chip code={p.code} colour={deptColor[p.dept]} />
            <span className="font-medium">{p.name}</span>
            <span className="ml-auto text-twin-muted">{p.dept}</span>
          </div>
          <div className="mt-1 text-twin-text">{p.text}</div>
          <div className="text-[10px] text-twin-muted">since {p.t}</div>
        </div>
      ))}
      {q && found.length === 0 && (
        <div className="mb-2 text-xs text-twin-muted">No {truth ? "" : "observed "}activity yet for “{query}”.</div>
      )}
      <div className="min-h-0 flex-1 space-y-0.5 overflow-auto text-[11px] leading-5">
        {lines.map((a, i) => (
          <div key={`${a.t}-${a.person}-${i}`} className="flex gap-1.5 truncate">
            <span className="font-mono text-twin-muted">{a.t.slice(0, 5)}</span>
            <Chip code={a.code} colour={deptColor[a.dept]} />
            <span className={cn("truncate", a.kind === "out" || a.kind === "outside_office" ? "text-twin-muted" : "text-twin-text")}>
              <span className="text-twin-muted">{a.name.split(" ")[0]} </span>
              {a.text}
            </span>
          </div>
        ))}
        {lines.length === 0 && !q && <div className="text-twin-muted">Nobody has badged in yet. Press Start.</div>}
      </div>
    </section>
  );
}
