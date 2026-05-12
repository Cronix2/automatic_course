import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SettingsGuard from "../components/SettingsGuard";
import SectionCard from "../components/SectionCard";
import { api, streamText, apiUrl } from "../api/client";
import {
  PlayIcon,
  StopIcon,
  MicIcon,
  SendIcon,
  SparkIcon,
  DownloadIcon,
  RefreshIcon,
  DatabaseIcon,
  BookIcon,
  ChatIcon,
  VoiceIcon,
} from "../components/Logo";
import { useStreamedTTS } from "../hooks/useStreamedTTS";

interface Provider {
  id: number;
  name: string;
  kind: string;
  model: string;
  is_default: boolean;
}

interface CourseContent {
  room_code: string;
  title: string;
  markdown: string;
  sections: string[];
}

interface CachedCourse {
  room_code: string;
  title: string;
  markdown: string;
  sections: string[];
  fetched_at: string | null;
  enhanced_markdown: string | null;
  enhanced_provider_kind: string | null;
  enhanced_provider_model: string | null;
  enhanced_style: string | null;
  enhanced_at: string | null;
  created_at: string;
  updated_at: string;
}

type Phase = "idle" | "fetching" | "enhancing" | "listening" | "error";

export default function PlayerPage() {
  return (
    <SettingsGuard>
      <PlayerInner />
    </SettingsGuard>
  );
}

/* ----------------------------- helpers ----------------------------------- */
function timeAgo(iso: string | null): string {
  if (!iso) return "jamais";
  const d = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - d);
  const s = Math.floor(diff / 1000);
  if (s < 60) return `il y a ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `il y a ${h} h`;
  const j = Math.floor(h / 24);
  return `il y a ${j} j`;
}

/* ============================== main page =============================== */
function PlayerInner() {
  const { roomCode } = useParams<{ roomCode: string }>();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerId, setProviderId] = useState<number | null>(null);
  const [course, setCourse] = useState<CourseContent | null>(null);
  const [enhanced, setEnhanced] = useState("");
  const [cache, setCache] = useState<CachedCourse | null>(null);
  const [chat, setChat] = useState<{ role: string; content: string }[]>([]);
  const [userInput, setUserInput] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [err, setErr] = useState<string | null>(null);
  const [twoFA, setTwoFA] = useState<{ challengeId: string } | null>(null);
  const [twoFACode, setTwoFACode] = useState("");
  const [twoFABusy, setTwoFABusy] = useState(false);

  const tts = useStreamedTTS();
  const enhanceAbort = useRef<AbortController | null>(null);
  const [enhanceInFlight, setEnhanceInFlight] = useState(false);

  /* ---------- initial load: providers + cache ---------- */
  useEffect(() => {
    (async () => {
      try {
        const ps = await api<Provider[]>("/api/settings/providers");
        setProviders(ps);
        const def = ps.find((p) => p.is_default) ?? ps[0];
        if (def) setProviderId(def.id);
      } catch (e) {
        setErr((e as Error).message);
      }
    })();
  }, []);

  useEffect(() => {
    if (!roomCode) return;
    (async () => {
      try {
        const c = await api<CachedCourse>(`/api/courses/${roomCode}`);
        setCache(c);
        if (c.markdown) {
          setCourse({
            room_code: c.room_code,
            title: c.title,
            markdown: c.markdown,
            sections: c.sections,
          });
        }
        if (c.enhanced_markdown) setEnhanced(c.enhanced_markdown);
      } catch {
        /* 404 → no cache yet, fine */
      }
    })();
  }, [roomCode]);

  /* ---------- save helpers ---------- */
  async function saveRawCache(c: CourseContent) {
    if (!roomCode) return;
    try {
      const saved = await api<CachedCourse>(`/api/courses/${roomCode}`, {
        method: "PUT",
        body: JSON.stringify({
          title: c.title,
          markdown: c.markdown,
          sections: c.sections,
        }),
      });
      setCache(saved);
    } catch (e) {
      console.warn("cache save raw failed", e);
    }
  }
  async function saveEnhancedCache(markdown: string) {
    if (!roomCode) return;
    const prov = providers.find((p) => p.id === providerId);
    try {
      const saved = await api<CachedCourse>(`/api/courses/${roomCode}/enhanced`, {
        method: "PUT",
        body: JSON.stringify({
          markdown,
          provider_kind: prov?.kind ?? null,
          provider_model: prov?.model ?? null,
          style: "concise_technical",
        }),
      });
      setCache(saved);
    } catch (e) {
      console.warn("cache save enhanced failed", e);
    }
  }

  /* ---------- fetch THM room ---------- */
  async function fetchRoom() {
    if (!roomCode) return;
    setPhase("fetching");
    setErr(null);
    try {
      const c = await api<CourseContent>("/api/thm/fetch", {
        method: "POST",
        body: JSON.stringify({ room_code: roomCode }),
      });
      setCourse(c);
      saveRawCache(c);
      setPhase("idle");
    } catch (e) {
      const msg = (e as Error).message;
      const m = msg.match(/thm_2fa_required.*?"challenge_id"\s*:\s*"([^"]+)"/);
      if (m) {
        setTwoFA({ challengeId: m[1] });
        setPhase("idle");
        setErr(null);
        return;
      }
      if (msg.includes("thm_captcha_blocked")) {
        setErr(
          "TryHackMe demande un CAPTCHA. Va dans Réglages → TryHackMe → " +
            "« CAPTCHA bloque la connexion » pour importer un cookie de session."
        );
        setPhase("error");
        return;
      }
      if (msg.includes("thm_session_expired")) {
        setErr(
          "Session TryHackMe expirée. Reconnecte-toi sur tryhackme.com puis " +
            "ré-importe ton cookie dans Réglages → TryHackMe."
        );
        setPhase("error");
        return;
      }
      setErr(msg);
      setPhase("error");
    }
  }

  async function submitTwoFA(e: React.FormEvent) {
    e.preventDefault();
    if (!twoFA) return;
    setTwoFABusy(true);
    setErr(null);
    try {
      await api("/api/thm/login/2fa", {
        method: "POST",
        body: JSON.stringify({
          challenge_id: twoFA.challengeId,
          code: twoFACode.trim(),
        }),
      });
      setTwoFA(null);
      setTwoFACode("");
      await fetchRoom();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setTwoFABusy(false);
    }
  }

  /* ---------- enhance (cancellable always) ---------- */
  async function enhance() {
    if (!course || !providerId) return;
    setEnhanced("");
    setPhase("enhancing");
    setErr(null);
    enhanceAbort.current?.abort();
    enhanceAbort.current = new AbortController();
    setEnhanceInFlight(true);
    let buf = "";
    try {
      await streamText(
        "/api/ai/enhance",
        { content: course, provider_id: providerId, style: "concise_technical" },
        (tok) => {
          buf += tok;
          setEnhanced((prev) => prev + tok);
        },
        enhanceAbort.current.signal
      );
      setPhase("idle");
      if (buf.trim()) saveEnhancedCache(buf);
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        setPhase("idle");
        return;
      }
      setErr((e as Error).message);
      setPhase("error");
    } finally {
      enhanceAbort.current = null;
      setEnhanceInFlight(false);
    }
  }
  function cancelEnhance() {
    enhanceAbort.current?.abort();
    enhanceAbort.current = null;
    setEnhanceInFlight(false);
    setPhase("idle");
  }

  /* ---------- mic / chat ---------- */
  async function startMic() {
    tts.stop();
    setPhase("listening");
    setErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        const form = new FormData();
        form.append("audio", blob, "input.webm");
        form.append("language", "fr");
        const resp = await fetch(apiUrl("/api/voice/stt"), {
          method: "POST",
          body: form,
        });
        const data = (await resp.json()) as { text: string };
        if (data.text) {
          setUserInput(data.text);
          await askAI(data.text);
        } else {
          setPhase("idle");
        }
      };
      rec.start();
      setTimeout(() => rec.state === "recording" && rec.stop(), 5000);
    } catch (e) {
      setErr("Micro indisponible : " + (e as Error).message);
      setPhase("error");
    }
  }

  async function askAI(question: string) {
    if (!providerId || !course) return;
    const messages = [
      {
        role: "system",
        content:
          "Tu es un assistant cybersécurité. Réponds en français, de manière concise, " +
          "en t'appuyant sur le cours fourni en contexte.",
      },
      {
        role: "user",
        content: `Cours en contexte:\n${course.markdown.slice(0, 8000)}`,
      },
      ...chat,
      { role: "user", content: question },
    ];
    setChat((c) => [...c, { role: "user", content: question }]);
    let answer = "";
    setPhase("enhancing");
    try {
      await streamText(
        "/api/ai/chat",
        { provider_id: providerId, messages, stream: true },
        (tok) => {
          answer += tok;
          setChat((c) => {
            const copy = [...c];
            if (copy[copy.length - 1]?.role === "assistant") {
              copy[copy.length - 1] = { role: "assistant", content: answer };
            } else {
              copy.push({ role: "assistant", content: answer });
            }
            return copy;
          });
        }
      );
      setPhase("idle");
      if (answer.trim()) tts.speak(answer);
    } catch (e) {
      setErr((e as Error).message);
      setPhase("error");
    }
  }

  /* ---------- derived ---------- */
  const phaseLabel: Record<Phase, string> = {
    idle: "Prêt",
    fetching: "Récupération…",
    enhancing: "IA en cours…",
    listening: "Écoute du micro…",
    error: "Erreur",
  };
  const ttsBusy = tts.status === "loading" || tts.status === "playing";

  /* ============================== render ============================== */
  return (
    <section className="space-y-6 max-w-5xl mx-auto">
      {/* ---------- top header ---------- */}
      <header className="rounded-2xl border border-line bg-gradient-to-br from-violet-500/10 via-bg-2/40 to-bg-1/20 p-5 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-violet-300/80">
              Salle TryHackMe
            </div>
            <h1 className="text-2xl sm:text-3xl font-semibold text-slate-50 truncate">
              {course?.title || roomCode}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-bg-2/70 border border-line px-2.5 py-1 text-slate-300">
                <span
                  className={
                    "h-1.5 w-1.5 rounded-full " +
                    (phase === "error"
                      ? "bg-rose-400"
                      : phase === "idle"
                      ? "bg-emerald-400"
                      : "bg-amber-300 animate-pulse")
                  }
                />
                {phaseLabel[phase]}
              </span>
              {tts.status !== "idle" && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-500/20 border border-violet-500/30 px-2.5 py-1 text-violet-200">
                  <VoiceIcon className="w-3 h-3" />
                  {tts.status === "loading" ? "Préparation audio…" : "Lecture"}
                  {tts.progress.total > 0 && (
                    <span className="opacity-70">
                      ({tts.progress.current}/{tts.progress.total})
                    </span>
                  )}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <select
              className="input max-w-xs"
              value={providerId ?? ""}
              onChange={(e) => setProviderId(Number(e.target.value))}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.model}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {err && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 text-rose-200 text-sm px-4 py-3 flex items-start justify-between gap-3">
          <span className="whitespace-pre-wrap">{err}</span>
          <button
            onClick={() => setErr(null)}
            className="text-rose-300/70 hover:text-rose-200 text-xs"
          >
            ✕
          </button>
        </div>
      )}

      {twoFA && (
        <TwoFAModal
          code={twoFACode}
          busy={twoFABusy}
          onChange={setTwoFACode}
          onCancel={() => {
            setTwoFA(null);
            setTwoFACode("");
          }}
          onSubmit={submitTwoFA}
        />
      )}

      {/* ---------- Step 1: Fetch ---------- */}
      <SectionCard
        accent="indigo"
        icon={<DownloadIcon className="w-5 h-5" />}
        title="Récupération du cours"
        subtitle="Scrape la salle depuis TryHackMe, tâche par tâche."
        action={
          cache?.fetched_at && (
            <span className="hidden sm:inline-flex items-center gap-1.5 text-xs text-slate-400">
              <DatabaseIcon className="w-3.5 h-3.5" />
              en cache · {timeAgo(cache.fetched_at)}
            </span>
          )
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="btn-primary"
            onClick={fetchRoom}
            disabled={phase === "fetching"}
          >
            {course ? (
              <>
                <RefreshIcon />
                {phase === "fetching" ? "Mise à jour…" : "Mettre à jour"}
              </>
            ) : (
              <>
                <DownloadIcon />
                {phase === "fetching" ? "Récupération…" : "Récupérer le cours"}
              </>
            )}
          </button>
          {course && (
            <div className="text-sm text-slate-300">
              <span className="font-medium text-slate-100">{course.title}</span>
              <span className="text-slate-500 ml-2 text-xs">
                {course.sections.length} sections ·{" "}
                {course.markdown.length.toLocaleString("fr-FR")} car.
              </span>
            </div>
          )}
        </div>

        {course && (
          <details className="mt-4 group">
            <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200 select-none">
              Voir la source brute envoyée à l'IA
            </summary>
            <div className="prose prose-invert prose-sm max-w-none mt-3 max-h-96 overflow-y-auto rounded-lg border border-line bg-bg-1/50 p-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {course.markdown}
              </ReactMarkdown>
            </div>
          </details>
        )}
      </SectionCard>

      {/* ---------- Step 2: Enhance ---------- */}
      <SectionCard
        accent="violet"
        icon={<SparkIcon className="w-5 h-5" />}
        title="Amélioration par l'IA"
        subtitle="Réécrit le cours pour une lecture fluide à voix haute."
        action={
          cache?.enhanced_at && (
            <span className="hidden sm:inline-flex items-center gap-1.5 text-xs text-slate-400">
              <DatabaseIcon className="w-3.5 h-3.5" />
              {cache.enhanced_provider_model || "IA"} ·{" "}
              {timeAgo(cache.enhanced_at)}
            </span>
          )
        }
      >
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-primary"
            onClick={enhance}
            disabled={!course || !providerId || phase === "enhancing"}
          >
            {enhanced ? (
              <>
                <RefreshIcon />
                {phase === "enhancing" ? "IA en cours…" : "Régénérer"}
              </>
            ) : (
              <>
                <SparkIcon />
                {phase === "enhancing" ? "IA en cours…" : "Réécrire avec l'IA"}
              </>
            )}
          </button>
          {(phase === "enhancing" || enhanceInFlight) && (
            <button className="btn-danger" onClick={cancelEnhance}>
              <StopIcon /> Arrêter l'IA
            </button>
          )}
        </div>

        {enhanced && (
          <article className="prose prose-invert prose-base max-w-none leading-relaxed mt-5 rounded-xl border border-line bg-bg-1/40 p-5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{enhanced}</ReactMarkdown>
          </article>
        )}
      </SectionCard>

      {/* ---------- Step 3: Speak ---------- */}
      <SectionCard
        accent="emerald"
        icon={<VoiceIcon className="w-5 h-5" />}
        title="Lecture audio"
        subtitle="Synthèse vocale streamée — la lecture commence pendant que les phrases suivantes se préparent."
      >
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="btn-primary"
            onClick={() => tts.speak(enhanced || course?.markdown || "")}
            disabled={ttsBusy || (!enhanced && !course)}
          >
            <PlayIcon />{" "}
            {tts.status === "loading" ? "Préparation…" : "Lire à voix haute"}
          </button>
          <button
            className="btn-danger"
            onClick={tts.stop}
            disabled={tts.status === "idle"}
          >
            <StopIcon /> Stop
          </button>
          {tts.progress.total > 0 && (
            <div className="ml-2 flex items-center gap-2 text-xs text-slate-400">
              <div className="h-1.5 w-32 rounded-full bg-bg-2 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-violet-400 to-emerald-400 transition-all"
                  style={{
                    width: `${(tts.progress.current / Math.max(1, tts.progress.total)) * 100}%`,
                  }}
                />
              </div>
              <span>
                {tts.progress.current}/{tts.progress.total}
              </span>
            </div>
          )}
          {tts.error && <span className="text-xs text-rose-300">{tts.error}</span>}
        </div>
      </SectionCard>

      {/* ---------- Step 4: Chat ---------- */}
      <SectionCard
        accent="sky"
        icon={<ChatIcon className="w-5 h-5" />}
        title="Conversation"
        subtitle="Pose une question sur le cours, l'IA répond et lit la réponse."
      >
        <ul className="space-y-3 mb-4 max-h-96 overflow-y-auto pr-1">
          {chat.length === 0 && (
            <li className="text-sm text-slate-500 italic">
              Aucune question pour l'instant.
            </li>
          )}
          {chat.map((m, i) => (
            <li
              key={i}
              className={
                "text-sm rounded-xl px-4 py-3 border " +
                (m.role === "user"
                  ? "bg-violet-500/10 border-violet-500/30 ml-8"
                  : "bg-bg-2/50 border-line mr-8")
              }
            >
              <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">
                {m.role === "user" ? "Toi" : "Assistant"}
              </div>
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              </div>
            </li>
          ))}
        </ul>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!userInput.trim()) return;
            const q = userInput;
            setUserInput("");
            askAI(q);
          }}
          className="flex gap-2"
        >
          <input
            className="input flex-1"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            placeholder="Pose une question (ex : « développe la partie sur ARP »)"
          />
          <button
            className="btn-ghost"
            type="button"
            onClick={startMic}
            title="Parler au micro"
          >
            <MicIcon />
          </button>
          <button className="btn-primary" type="submit">
            <SendIcon /> Envoyer
          </button>
        </form>
      </SectionCard>

      <footer className="text-center text-xs text-slate-500 pt-2 pb-8 flex items-center justify-center gap-2">
        <BookIcon className="w-3 h-3" /> Tout le contenu généré reste local.
      </footer>
    </section>
  );
}

/* --------------------------- 2FA modal --------------------------------- */
function TwoFAModal({
  code,
  busy,
  onChange,
  onCancel,
  onSubmit,
}: {
  code: string;
  busy: boolean;
  onChange: (v: string) => void;
  onCancel: () => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <form
        onSubmit={onSubmit}
        className="rounded-2xl border border-line bg-bg-1 p-6 max-w-sm w-full space-y-4 shadow-2xl"
      >
        <div>
          <h2 className="text-lg font-semibold">Code 2FA TryHackMe</h2>
          <p className="text-sm text-slate-400 mt-1">
            Saisis le code à 6 chiffres de ton application d'authentification.
          </p>
        </div>
        <input
          autoFocus
          inputMode="numeric"
          pattern="[0-9]{4,8}"
          maxLength={8}
          className="input tracking-[0.4em] text-center text-lg"
          value={code}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))}
          placeholder="••••••"
          required
        />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-ghost"
            onClick={onCancel}
            disabled={busy}
          >
            Annuler
          </button>
          <button
            className="btn-primary"
            type="submit"
            disabled={busy || code.length < 4}
          >
            {busy ? "Validation…" : "Valider"}
          </button>
        </div>
      </form>
    </div>
  );
}
