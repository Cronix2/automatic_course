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
    violet:   "from-violet-500/25 to-violet-500/0  text-violet-300  ring-violet-400/20",
    indigo:   "from-indigo-500/25 to-indigo-500/0  text-indigo-300  ring-indigo-400/20",
    emerald:  "from-emerald-500/25 to-emerald-500/0 text-emerald-300 ring-emerald-400/20",
    amber:    "from-amber-500/25 to-amber-500/0   text-amber-300   ring-amber-400/20",
    rose:     "from-rose-500/25 to-rose-500/0     text-rose-300    ring-rose-400/20",
    sky:      "from-sky-500/25 to-sky-500/0       text-sky-300     ring-sky-400/20",
  };
  const cls = accentMap[accent] ?? accentMap.violet;
  return (
    <section
      className={
        "rounded-2xl border border-line bg-gradient-to-b from-bg-2/60 to-bg-1/40 " +
        "shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_8px_30px_-8px_rgba(0,0,0,0.5)] " +
        "p-5 sm:p-6 " + className
      }
    >
      <header className="flex items-start gap-4 mb-5">
        {icon && (
          <div
            className={
              "shrink-0 grid place-items-center w-10 h-10 rounded-xl " +
              "bg-gradient-to-br ring-1 " + cls
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
