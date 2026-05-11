import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import SettingsGuard from "../components/SettingsGuard";
import { api } from "../api/client";

interface Suggested {
  room_code: string;
  title: string;
  description: string;
  difficulty: string;
  tags: string[];
}

const ROOM_URL_RE = /tryhackme\.com\/(?:room|r)\/([A-Za-z0-9_-]+)/i;
const SLUG_RE = /^[A-Za-z0-9_-]+$/;

function parseRef(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  const m = v.match(ROOM_URL_RE);
  if (m) return m[1].toLowerCase();
  if (SLUG_RE.test(v)) return v.toLowerCase();
  return null;
}

const DIFF_BADGES: Record<string, string> = {
  info: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  easy: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  medium: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  hard: "bg-rose-500/10 text-rose-300 border-rose-500/30",
};

export default function CoursesPage() {
  return (
    <SettingsGuard>
      <CoursesInner />
    </SettingsGuard>
  );
}

function CoursesInner() {
  const nav = useNavigate();
  const [input, setInput] = useState("");
  const [suggested, setSuggested] = useState<Suggested[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Suggested[]>("/api/thm/suggested")
      .then(setSuggested)
      .catch((e) => setErr((e as Error).message));
    try {
      const raw = localStorage.getItem("ac.recentRooms");
      if (raw) setRecent(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  const parsed = useMemo(() => parseRef(input), [input]);

  function go(code: string) {
    try {
      const next = [code, ...recent.filter((r) => r !== code)].slice(0, 6);
      localStorage.setItem("ac.recentRooms", JSON.stringify(next));
    } catch {
      /* ignore */
    }
    nav(`/player/${encodeURIComponent(code)}`);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!parsed) {
      setErr("Entre un nom de room (ex: nmap) ou une URL TryHackMe.");
      return;
    }
    setErr(null);
    go(parsed);
  }

  return (
    <section className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Choisir un cours</h1>
        <p className="text-slate-400 text-sm mt-1">
          Colle l'URL d'une room TryHackMe ou tape son identifiant. Tu peux
          aussi piocher dans les suggestions ci-dessous.
        </p>
      </header>

      <form onSubmit={submit} className="card space-y-3">
        <label className="label">Room TryHackMe</label>
        <div className="flex gap-3">
          <input
            className="input flex-1"
            placeholder="nmap   ou   https://tryhackme.com/room/nmap"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            autoFocus
          />
          <button className="btn-primary" type="submit" disabled={!parsed}>
            Lancer →
          </button>
        </div>
        {input && (
          <div className="text-xs text-slate-500">
            {parsed ? (
              <>
                Sera ouvert :{" "}
                <code className="text-violet-400">{parsed}</code>
              </>
            ) : (
              <span className="text-amber-300">
                Format invalide. Exemples : <code>introtonetworking</code> ou{" "}
                <code>https://tryhackme.com/room/nmap</code>
              </span>
            )}
          </div>
        )}
        {err && <div className="text-rose-300 text-sm">{err}</div>}
      </form>

      {recent.length > 0 && (
        <section>
          <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-3">
            Récents
          </h2>
          <div className="flex flex-wrap gap-2">
            {recent.map((r) => (
              <button key={r} onClick={() => go(r)} className="btn-ghost">
                {r}
              </button>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-3">
          Suggestions
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {suggested.map((s) => (
            <button
              key={s.room_code}
              onClick={() => go(s.room_code)}
              className="text-left rounded-xl border border-line hover:border-line-strong bg-bg-2/40 hover:bg-bg-2/70 transition-colors p-4 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{s.title}</span>
                <span
                  className={`text-[10px] uppercase rounded-full px-2 py-0.5 border ${
                    DIFF_BADGES[s.difficulty] ?? DIFF_BADGES.info
                  }`}
                >
                  {s.difficulty}
                </span>
              </div>
              <div className="text-xs text-slate-400">{s.description}</div>
              <div className="text-[10px] text-slate-500 font-mono">
                {s.room_code}
              </div>
            </button>
          ))}
        </div>
      </section>
    </section>
  );
}
