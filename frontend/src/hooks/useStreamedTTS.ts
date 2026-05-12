/**
 * Streamed TTS: splits text into ~sentence-sized chunks, fetches them
 * in parallel (with a small prefetch window) and plays them back in order
 * so the user hears audio almost immediately while later chunks synthesise.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "../api/client";

/* ----------------------------- Text cleaning ----------------------------- */
export function stripMarkdownForTTS(md: string): string {
  let t = md;
  t = t.replace(/```[\s\S]*?```/g, " ");
  t = t.replace(/`([^`]+)`/g, "$1");
  t = t.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  t = t.replace(/^#{1,6}\s+/gm, "");
  t = t.replace(/(\*\*|__)(.*?)\1/g, "$2");
  t = t.replace(/(\*|_)(.*?)\1/g, "$2");
  t = t.replace(/~~(.*?)~~/g, "$1");
  t = t.replace(/^\s*[-*+]\s+/gm, "");
  t = t.replace(/^\s*\d+\.\s+/gm, "");
  t = t.replace(/^>\s?/gm, "");
  t = t.replace(/^\s*[-*_]{3,}\s*$/gm, "");
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  return t;
}

/* ------------------------- Sentence segmentation ------------------------- */
const MIN_CHUNK = 60;
const MAX_CHUNK = 280;

export function splitIntoChunks(text: string): string[] {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return [];
  // Split on sentence terminators, keep them attached.
  const pieces = clean.match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g) ?? [clean];

  const chunks: string[] = [];
  let buf = "";
  for (const raw of pieces) {
    const s = raw.trim();
    if (!s) continue;
    if ((buf + " " + s).trim().length > MAX_CHUNK && buf.length >= MIN_CHUNK) {
      chunks.push(buf.trim());
      buf = s;
    } else {
      buf = buf ? buf + " " + s : s;
    }
    // Flush if we already exceed the soft minimum
    if (buf.length >= MIN_CHUNK && /[.!?…]\s*$/.test(buf)) {
      chunks.push(buf.trim());
      buf = "";
    }
  }
  if (buf.trim()) chunks.push(buf.trim());

  // Merge any tiny tail back into the previous chunk
  if (chunks.length >= 2 && chunks[chunks.length - 1].length < MIN_CHUNK) {
    const tail = chunks.pop()!;
    chunks[chunks.length - 1] += " " + tail;
  }
  return chunks;
}

/* ----------------------------- Streaming hook ---------------------------- */
type Status = "idle" | "loading" | "playing" | "error";

export interface StreamedTTSState {
  status: Status;
  progress: { current: number; total: number };
  error: string | null;
  speak: (text: string) => Promise<void>;
  stop: () => void;
}

const PREFETCH_AHEAD = 2; // how many chunks to fetch ahead of the playing one

export function useStreamedTTS(): StreamedTTSState {
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [error, setError] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const urlsRef = useRef<string[]>([]);
  const stoppedRef = useRef(false);

  // Lazily create a single Audio element (no need for the user to "see" it
  // since the visible <audio> control wouldn't help with multi-chunk anyway).
  function getAudio(): HTMLAudioElement {
    if (!audioRef.current) {
      audioRef.current = new Audio();
      audioRef.current.preload = "auto";
    }
    return audioRef.current;
  }

  const stop = useCallback(() => {
    stoppedRef.current = true;
    abortRef.current?.abort();
    const a = audioRef.current;
    if (a) {
      try { a.pause(); } catch { /* noop */ }
      a.removeAttribute("src");
      a.load();
    }
    urlsRef.current.forEach((u) => URL.revokeObjectURL(u));
    urlsRef.current = [];
    setStatus("idle");
    setProgress({ current: 0, total: 0 });
  }, []);

  const speak = useCallback(async (text: string) => {
    stop();
    stoppedRef.current = false;
    setError(null);

    const clean = stripMarkdownForTTS(text);
    const chunks = splitIntoChunks(clean);
    if (chunks.length === 0) {
      setError("Aucun texte lisible.");
      setStatus("error");
      return;
    }

    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;

    // Pre-allocate URL slots. Each slot will be filled by a fetch promise.
    const urls: (Promise<string> | null)[] = new Array(chunks.length).fill(null);

    async function fetchChunk(idx: number): Promise<string> {
      const resp = await fetch(apiUrl("/api/voice/tts"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: chunks[idx] }),
        signal,
      });
      if (!resp.ok) {
        const body = await resp.text().catch(() => "");
        throw new Error(`TTS ${resp.status}: ${body.slice(0, 200)}`);
      }
      const blob = await resp.blob();
      if (blob.size < 100) throw new Error("TTS a renvoyé un audio vide.");
      const url = URL.createObjectURL(blob);
      urlsRef.current.push(url);
      return url;
    }

    function ensureFetched(idx: number) {
      if (idx >= chunks.length || idx < 0) return;
      if (urls[idx] == null) urls[idx] = fetchChunk(idx);
    }

    setStatus("loading");
    setProgress({ current: 0, total: chunks.length });

    // Kick off the first PREFETCH_AHEAD + 1 fetches in parallel.
    for (let i = 0; i <= PREFETCH_AHEAD && i < chunks.length; i++) {
      ensureFetched(i);
    }

    const audio = getAudio();
    try {
      for (let i = 0; i < chunks.length; i++) {
        if (stoppedRef.current) return;
        // Make sure the next ones are already queued.
        ensureFetched(i + PREFETCH_AHEAD);

        const url = await urls[i]!;
        if (stoppedRef.current) return;

        audio.src = url;
        audio.load();
        setStatus("playing");
        setProgress({ current: i + 1, total: chunks.length });

        try {
          await audio.play();
        } catch (e) {
          throw new Error(
            "Lecture audio refusée par le navigateur : " +
              (e as Error).message +
              ". Clique sur la page puis relance.",
          );
        }

        await new Promise<void>((resolve, reject) => {
          const onEnded = () => { cleanup(); resolve(); };
          const onError = () => {
            cleanup();
            const code = audio.error?.code;
            reject(new Error(`Audio error code=${code ?? "?"}`));
          };
          const onAbort = () => { cleanup(); resolve(); };
          function cleanup() {
            audio.removeEventListener("ended", onEnded);
            audio.removeEventListener("error", onError);
            signal.removeEventListener("abort", onAbort);
          }
          audio.addEventListener("ended", onEnded);
          audio.addEventListener("error", onError);
          signal.addEventListener("abort", onAbort);
          if (stoppedRef.current) onAbort();
        });
      }
      if (!stoppedRef.current) {
        setStatus("idle");
        setProgress({ current: 0, total: 0 });
      }
    } catch (e) {
      if ((e as Error).name === "AbortError" || stoppedRef.current) {
        setStatus("idle");
        return;
      }
      setError((e as Error).message);
      setStatus("error");
    } finally {
      urlsRef.current.forEach((u) => URL.revokeObjectURL(u));
      urlsRef.current = [];
    }
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return { status, progress, error, speak, stop };
}
