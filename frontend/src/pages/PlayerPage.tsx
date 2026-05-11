import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import SettingsGuard from "../components/SettingsGuard";
import { api, apiUrl, streamText } from "../api/client";
import {
  PlayIcon,
  StopIcon,
  MicIcon,
  SendIcon,
  SparkIcon,
  DownloadIcon,
} from "../components/Logo";

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

type Phase = "idle" | "fetching" | "enhancing" | "speaking" | "listening" | "error";

export default function PlayerPage() {
  return (
    <SettingsGuard>
      <PlayerInner />
    </SettingsGuard>
  );
}

function PlayerInner() {
  const { roomCode } = useParams<{ roomCode: string }>();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerId, setProviderId] = useState<number | null>(null);
  const [course, setCourse] = useState<CourseContent | null>(null);
  const [enhanced, setEnhanced] = useState("");
  const [chat, setChat] = useState<{ role: string; content: string }[]>([]);
  const [userInput, setUserInput] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [err, setErr] = useState<string | null>(null);
  const [twoFA, setTwoFA] = useState<{ challengeId: string } | null>(null);
  const [twoFACode, setTwoFACode] = useState("");
  const [twoFABusy, setTwoFABusy] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);
  const enhanceAbort = useRef<AbortController | null>(null);

  // ---- Initial load ------------------------------------------------------
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

  // ---- Step 1: fetch THM room -------------------------------------------
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
      setPhase("idle");
    } catch (e) {
      const msg = (e as Error).message;
      // Backend signals 2FA with status 401 and a JSON body containing the
      // challenge id. The api() helper throws "{status} {statusText}: {body}".
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
          "« CAPTCHA bloque la connexion ? Importer un cookie de session » " +
          "pour contourner."
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

  // ---- Step 2: enhance via AI (streaming) -------------------------------
  async function enhance() {
    if (!course || !providerId) return;
    setEnhanced("");
    setPhase("enhancing");
    enhanceAbort.current?.abort();
    enhanceAbort.current = new AbortController();
    try {
      await streamText(
        "/api/ai/enhance",
        { content: course, provider_id: providerId, style: "concise_technical" },
        (tok) => setEnhanced((prev) => prev + tok),
        enhanceAbort.current.signal
      );
      setPhase("idle");
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setErr((e as Error).message);
        setPhase("error");
      }
    }
  }

  // ---- Step 3: speak ----------------------------------------------------
  const lastBlobUrl = useRef<string | null>(null);

  async function speak(text: string) {
    if (!audioRef.current || !text.trim()) return;
    try {
      setPhase("speaking");
      const resp = await fetch(apiUrl("/api/voice/tts"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!resp.ok) throw new Error(`TTS ${resp.status}: ${await resp.text()}`);
      const blob = await resp.blob();
      if (lastBlobUrl.current) URL.revokeObjectURL(lastBlobUrl.current);
      const url = URL.createObjectURL(blob);
      lastBlobUrl.current = url;
      audioRef.current.src = url;
      await audioRef.current.play().catch(() => undefined);
    } catch (e) {
      setErr((e as Error).message);
      setPhase("error");
    }
  }

  function stopSpeaking() {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setPhase("idle");
  }

  // ---- Interruption via mic --------------------------------------------
  async function startMic() {
    stopSpeaking();
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
      // 5s push-to-talk window; UI button can stop early
      setTimeout(() => rec.state === "recording" && rec.stop(), 5000);
    } catch (e) {
      setErr("Micro indisponible: " + (e as Error).message);
      setPhase("error");
    }
  }

  // ---- Chat / Q&A -------------------------------------------------------
  async function askAI(question: string) {
    if (!providerId || !course) return;
    const messages = [
      {
        role: "system",
        content:
          "Tu es un assistant cybersécurité. Réponds en français, de manière concise, " +
          "en t'appuyant sur le cours fourni en contexte.",
      },
      { role: "user", content: `Cours en contexte:\n${course.markdown.slice(0, 8000)}` },
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
      if (answer.trim()) speak(answer);
    } catch (e) {
      setErr((e as Error).message);
      setPhase("error");
    }
  }

  // ---- Render -----------------------------------------------------------
  return (
    <section className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Cours : {roomCode}</h1>
          <p className="text-slate-400 text-sm">Phase : {phase}</p>
        </div>
        <select
          className="input max-w-xs"
          value={providerId ?? ""}
          onChange={(e) => setProviderId(Number(e.target.value))}
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.kind} / {p.model})
            </option>
          ))}
        </select>
      </header>

      {err && (
        <div className="card border-rose-400/30 text-rose-200 text-sm">{err}</div>
      )}

      {twoFA && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <form
            onSubmit={submitTwoFA}
            className="card max-w-sm w-full space-y-4"
          >
            <div>
              <h2 className="text-lg font-semibold">Code 2FA TryHackMe</h2>
              <p className="text-sm text-slate-400 mt-1">
                Saisis le code à 6 chiffres de ton application
                d'authentification.
              </p>
            </div>
            <input
              autoFocus
              inputMode="numeric"
              pattern="[0-9]{4,8}"
              maxLength={8}
              className="input tracking-[0.4em] text-center text-lg"
              value={twoFACode}
              onChange={(e) =>
                setTwoFACode(e.target.value.replace(/\D/g, ""))
              }
              placeholder="••••••"
              required
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setTwoFA(null);
                  setTwoFACode("");
                }}
                disabled={twoFABusy}
              >
                Annuler
              </button>
              <button
                className="btn-primary"
                type="submit"
                disabled={twoFABusy || twoFACode.length < 4}
              >
                {twoFABusy ? "Validation…" : "Valider"}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-semibold mb-3">1. Récupérer le cours</h2>
          <button
            className="btn-primary"
            onClick={fetchRoom}
            disabled={phase === "fetching"}
          >
            <DownloadIcon />
            {phase === "fetching" ? "Récupération…" : "Récupérer depuis TryHackMe"}
          </button>
          {course && (
            <div className="mt-4 text-sm text-slate-300">
              <div className="font-medium">{course.title}</div>
              <div className="text-xs text-slate-500">
                {course.sections.length} sections · {course.markdown.length} caractères
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="font-semibold mb-3">2. Améliorer & lire</h2>
          <div className="flex gap-2 flex-wrap">
            <button
              className="btn-primary"
              onClick={enhance}
              disabled={!course || !providerId || phase === "enhancing"}
            >
              <SparkIcon />
              {phase === "enhancing" ? "IA en cours…" : "Réécrire avec l'IA"}
            </button>
            <button
              className="btn-ghost"
              onClick={() => enhanced && speak(enhanced)}
              disabled={!enhanced || phase === "speaking"}
            >
              <PlayIcon /> Lire à voix haute
            </button>
            <button
              className="btn-danger"
              onClick={stopSpeaking}
              disabled={phase !== "speaking"}
            >
              <StopIcon /> Interrompre
            </button>
            <button className="btn-ghost" onClick={startMic}>
              <MicIcon /> Parler
            </button>
          </div>
          <audio
            ref={audioRef}
            onEnded={() => {
              setPhase("idle");
              if (lastBlobUrl.current) {
                URL.revokeObjectURL(lastBlobUrl.current);
                lastBlobUrl.current = null;
              }
            }}
            hidden
          />
        </div>
      </div>

      {enhanced && (
        <div className="card">
          <h2 className="font-semibold mb-3">Cours réécrit</h2>
          <pre className="whitespace-pre-wrap text-sm text-slate-200 font-sans">
            {enhanced}
          </pre>
        </div>
      )}

      <div className="card">
        <h2 className="font-semibold mb-3">Conversation</h2>
        <ul className="space-y-3 mb-4 max-h-80 overflow-y-auto">
          {chat.map((m, i) => (
            <li
              key={i}
              className={`text-sm rounded-xl px-3 py-2 border ${
                m.role === "user"
                  ? "bg-violet-500/10 border-violet-500/30"
                  : "bg-bg-2/40 border-line"
              }`}
            >
              <div className="text-[10px] uppercase text-slate-400 mb-1">
                {m.role}
              </div>
              {m.content}
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
            placeholder="Pose une question (ex: « développe la partie sur ARP »)"
          />
          <button className="btn-primary" type="submit">
            <SendIcon /> Envoyer
          </button>
        </form>
      </div>
    </section>
  );
}
