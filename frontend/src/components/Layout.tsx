import { NavLink, Outlet } from "react-router-dom";
import { useEffect } from "react";
import { useSettingsStore } from "../store/settings";
import Logo from "./Logo";

export default function Layout() {
  const refresh = useSettingsStore((s) => s.refresh);
  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line backdrop-blur-md bg-bg-0/70 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Logo className="w-9 h-9" />
            <div>
              <div className="font-semibold tracking-tight">Automatic Course</div>
              <div className="text-[11px] text-slate-400 -mt-0.5">
                THM → IA → vocal
              </div>
            </div>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            <NavTab to="/">Accueil</NavTab>
            <NavTab to="/courses">Cours</NavTab>
            <NavTab to="/settings">Paramètres</NavTab>
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-10">
        <Outlet />
      </main>

      <footer className="border-t border-line text-xs text-slate-500 px-6 py-4 text-center">
        Auto-hébergé · STT/TTS local · v0.1.0
      </footer>
    </div>
  );
}

function NavTab({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `px-3 py-2 rounded-lg transition-colors ${
          isActive
            ? "bg-white/[0.08] text-white"
            : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]"
        }`
      }
    >
      {children}
    </NavLink>
  );
}
