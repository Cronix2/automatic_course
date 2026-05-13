import React from "react";

/**
 * Modern dashboard-style card with icon header + title + subtitle.
 * Used across PlayerPage & SettingsPage for a consistent look.
 */
export default function SectionCard({
  icon,
  title,
  subtitle,
  action,
  accent = "violet",
  children,
  className = "",
}: {
  icon?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  accent?: "violet" | "indigo" | "emerald" | "amber" | "rose" | "sky";
  children?: React.ReactNode;
  className?: string;
}) {
  const accentMap: Record<string, string> = {
    violet:   "bg-violet-500/15  text-violet-300  ring-violet-400/25",
    indigo:   "bg-indigo-500/15  text-indigo-300  ring-indigo-400/25",
    emerald:  "bg-emerald-500/15 text-emerald-300 ring-emerald-400/25",
    amber:    "bg-amber-500/15   text-amber-300   ring-amber-400/25",
    rose:     "bg-rose-500/15    text-rose-300    ring-rose-400/25",
    sky:      "bg-sky-500/15     text-sky-300     ring-sky-400/25",
  };
  const cls = accentMap[accent] ?? accentMap.violet;
  return (
    <section
      className={
        "rounded-2xl border border-line bg-bg-1/70 " +
        "p-5 sm:p-6 " + className
      }
    >
      <header className="flex items-start gap-4 mb-5">
        {icon && (
          <div
            className={
              "shrink-0 grid place-items-center w-10 h-10 rounded-xl ring-1 " + cls
            }
          >
            {icon}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h2 className="text-base sm:text-lg font-semibold text-slate-100 leading-tight">
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs sm:text-[13px] text-slate-400 mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div>{children}</div>
    </section>
  );
}
