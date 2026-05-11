import { Navigate } from "react-router-dom";
import { useSettingsStore } from "../store/settings";

/**
 * Blocks access to pages that need a fully configured app.
 * Shows a clear error pointing to Settings when something is missing.
 */
export default function SettingsGuard({ children }: { children: React.ReactNode }) {
  const status = useSettingsStore((s) => s.status);
  if (!status) {
    return (
      <div className="card text-slate-300">
        Chargement de la configuration…
      </div>
    );
  }
  if (status.overall_ok) return <>{children}</>;

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-2">Configuration incomplète</h2>
      <p className="text-slate-400 text-sm mb-4">
        Tu dois compléter les paramètres ci-dessous avant d'utiliser l'application.
      </p>
      <ul className="space-y-2 mb-6 text-sm">
        <StatusRow label="TryHackMe" s={status.thm} />
        <StatusRow label="Providers IA" s={status.providers} />
        <StatusRow label="Modèles locaux" s={status.local_models} />
      </ul>
      <Navigate to="/settings" replace />
    </div>
  );
}

function StatusRow({ label, s }: { label: string; s: { ok: boolean; message: string } }) {
  return (
    <li className="flex items-center justify-between border-b border-white/5 py-2">
      <span>{label}</span>
      {s.ok ? (
        <span className="badge-ok">✓ {s.message}</span>
      ) : (
        <span className="badge-err">✗ {s.message}</span>
      )}
    </li>
  );
}
