import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { NAVIGATION, sectionPath } from "./navigation";

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col bg-slate-900 text-slate-300">
      <div className="px-5 py-5">
        <div className="text-base font-semibold text-white">Workplace Twin</div>
        <div className="text-xs text-slate-400">Smart office simulator</div>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAVIGATION.map((section) => {
          const Icon = section.icon;
          return (
            <NavLink
              key={section.slug}
              to={sectionPath(section)}
              end={section.slug === ""}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive ? "bg-slate-800 text-white" : "hover:bg-slate-800/60 hover:text-white",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {section.label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
