import { Link } from "react-router-dom";
import { useSettingsStore } from "../store/settings";

export default function HomePage() {
  const status = useSettingsStore((s) => s.status);
  const ready = status?.overall_ok ?? false;

  return (
    <section className="space-y-8">
      <div className="card relative overflow-hidden">
        <h1 className="text-3xl font-semibold tracking-tight mb-2">
          Tes cours TryHackMe, en{" "}
          <span className="text-violet-400">vocal, augmentés</span>{" "}
          par IA.
        </h1>
        <p className="text-slate-400 max-w-2xl">
          Sélectionne un cours, l'IA le réécrit (plus concis, plus technique), un
          moteur TTS local le lit à voix haute. Interromps-le à la voix pour
          poser des questions.
        </p>

        <div className="mt-6 flex gap-3">
          {ready ? (
            <Link to="/courses" className="btn-primary">
              Commencer un cours →
            </Link>
          ) : (
            <Link to="/settings" className="btn-primary">
              Configurer l'application →
            </Link>
          )}
          <a
            href="https://github.com/Cronix2/automatic_course"
            target="_blank"
            rel="noreferrer"
            className="btn-ghost"
          >
            Documentation
          </a>
        </div>
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <Feature title="100 % local" desc="STT (faster-whisper) et TTS (Piper) tournent sur ta machine." />
        <Feature title="Multi-providers" desc="OpenRouter, OpenAI, Anthropic, GitHub Models, Ollama." />
        <Feature title="Sécurisé" desc="Secrets AES-256-GCM, OAuth GitHub, headers durcis." />
      </div>
    </section>
  );
}

function Feature({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="card">
      <div className="text-sm font-semibold text-violet-400 mb-1">{title}</div>
      <div className="text-sm text-slate-400">{desc}</div>
    </div>
  );
}
