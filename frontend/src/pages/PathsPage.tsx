import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import SettingsGuard from "../components/SettingsGuard";
import SectionCard from "../components/SectionCard";
import { api } from "../api/client";
import { BookIcon, DownloadIcon, RefreshIcon } from "../components/Logo";

interface PathSummary {
  slug: string;
  title: string;
  description: string;
  difficulty: string;
  rooms_count: number;
}

interface PathRoom {
  room_code: string;
  title: string;
  module: string;
}

interface PathDetail {
  slug: string;
  title: string;
  description: string;
  rooms: PathRoom[];
}

const DIFF_BADGES: Record<string, string> = {
  info: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  easy: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  medium: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  hard: "bg-rose-500/10 text-rose-300 border-rose-500/30",
};

/* ============================== List view =============================== */
export default function PathsPage() {
  return (
    <SettingsGuard>
      <PathsList />
    </SettingsGuard>
  );
}

function PathsList() {
  const [paths, setPaths] = useState<PathSummary[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<PathSummary[]>("/api/thm/paths")
      .then((p) => {
        setPaths(p);
        setLoading(false);
      })
      .catch((e) => {
        setErr((e as Error).message);
        setLoading(false);
      });
  }, []);

  return (
    <section className="space-y-6 max-w-5xl mx-auto">
      <header className="rounded-2xl border border-line bg-bg-1/70 p-5 sm:p-6">
        <h1 className="text-2xl sm:text-3xl font-semibold text-slate-50">
          Chemins de formation
        </h1>
        <p className="text-slate-400 text-sm mt-1.5">
          Parcours TryHackMe transformés en cours audio. Choisis un chemin
          pour voir ses rooms et les lancer en lecture vocale.
        </p>
      </header>

      {err && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 text-rose-200 text-sm px-4 py-3">
          {err}
        </div>
      )}

      <SectionCard
        accent="indigo"
        icon={<BookIcon className="w-5 h-5" />}
        title="Catalogue"
        subtitle="Les chemins officiels de TryHackMe."
      >
        {loading ? (
          <div className="text-sm text-slate-400 italic">Chargement…</div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {paths.map((p) => (
              <Link
                key={p.slug}
                to={`/paths/${p.slug}`}
                className="text-left rounded-xl border border-line hover:border-line-strong bg-bg-2/40 hover:bg-bg-2/70 transition-colors p-4 space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-100">{p.title}</span>
                  <span
                    className={`text-[10px] uppercase rounded-full px-2 py-0.5 border ${
                      DIFF_BADGES[p.difficulty] ?? DIFF_BADGES.info
                    }`}
                  >
                    {p.difficulty}
                  </span>
                </div>
                <div className="text-xs text-slate-400">{p.description}</div>
                <div className="text-[10px] text-slate-500 font-mono">
                  {p.rooms_count} rooms · {p.slug}
                </div>
              </Link>
            ))}
          </div>
        )}
      </SectionCard>
    </section>
  );
}

/* ============================ Detail view =============================== */
export function PathDetailPage() {
  return (
    <SettingsGuard>
      <PathDetailInner />
    </SettingsGuard>
  );
}

function PathDetailInner() {
  const { slug } = useParams<{ slug: string }>();
  const nav = useNavigate();
  const [data, setData] = useState<PathDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    if (!slug) return;
    setLoading(true);
    setErr(null);
    try {
      const d = await api<PathDetail>(`/api/thm/paths/${slug}`);
      setData(d);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  // Group rooms by module
  const grouped: { module: string; rooms: PathRoom[] }[] = [];
  if (data) {
    const map = new Map<string, PathRoom[]>();
    for (const r of data.rooms) {
      const key = r.module || "Rooms";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(r);
    }
    for (const [k, v] of map) grouped.push({ module: k, rooms: v });
  }

  return (
    <section className="space-y-6 max-w-5xl mx-auto">
      <header className="rounded-2xl border border-line bg-bg-1/70 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-slate-400">
              Chemin TryHackMe
            </div>
            <h1 className="text-2xl sm:text-3xl font-semibold text-slate-50 truncate">
              {data?.title || slug}
            </h1>
            {data?.description && (
              <p className="text-sm text-slate-400 mt-2">{data.description}</p>
            )}
          </div>
          <button className="btn-ghost shrink-0" onClick={load} disabled={loading}>
            <RefreshIcon /> {loading ? "Chargement…" : "Recharger"}
          </button>
        </div>
      </header>

      {err && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 text-rose-200 text-sm px-4 py-3">
          {err}
        </div>
      )}

      {loading && !data && (
        <SectionCard accent="indigo" title="Récupération en cours…">
          <p className="text-sm text-slate-400">
            Le contenu est scrappé en direct depuis TryHackMe. Cela peut
            prendre une dizaine de secondes.
          </p>
        </SectionCard>
      )}

      {data && grouped.length === 0 && !loading && (
        <SectionCard accent="amber" title="Aucune room détectée">
          <p className="text-sm text-slate-400">
            La page n'a pas exposé de room. Vérifie que ton compte TryHackMe
            a accès à ce chemin.
          </p>
        </SectionCard>
      )}

      {grouped.map((g, i) => (
        <SectionCard
          key={i}
          accent={i % 2 === 0 ? "indigo" : "violet"}
          icon={<BookIcon className="w-5 h-5" />}
          title={g.module}
          subtitle={`${g.rooms.length} room${g.rooms.length > 1 ? "s" : ""}`}
        >
          <ul className="space-y-2">
            {g.rooms.map((r) => (
              <li
                key={r.room_code}
                className="rounded-xl border border-line bg-bg-2/40 hover:border-violet-400/30 hover:bg-bg-2/70 transition-colors px-4 py-3 flex flex-wrap items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="font-medium text-slate-100 truncate">
                    {r.title}
                  </div>
                  <div className="text-xs text-slate-500 font-mono">
                    {r.room_code}
                  </div>
                </div>
                <button
                  className="btn-primary text-xs"
                  onClick={() => nav(`/player/${encodeURIComponent(r.room_code)}`)}
                >
                  <DownloadIcon /> Ouvrir
                </button>
              </li>
            ))}
          </ul>
        </SectionCard>
      ))}
    </section>
  );
}
