import { useEffect, useState } from "react";
import { api, apiUrl } from "../api/client";
import { useSettingsStore } from "../store/settings";
import SectionCard from "../components/SectionCard";
import {
  GitHubIcon,
  VoiceIcon,
  KeyIcon,
  ShieldIcon,
  CogIcon,
  PlusIcon,
  TrashIcon,
  DownloadIcon,
  CheckIcon,
  SaveIcon,
  RefreshIcon,
} from "../components/Logo";

// ---- Types -----------------------------------------------------------------
interface Provider {
  id: number;
  name: string;
  kind: string;
  model: string;
  base_url: string | null;
  auth_method: "api_key" | "oauth" | "none";
  has_credentials: boolean;
  is_default: boolean;
}interface THMStatus {
  configured: boolean;
  session_valid: boolean;
  email_masked: string | null;
}

interface Preset {
  kind: string;
  label: string;
  description: string;
  default_model: string;
  default_base_url: string | null;
  auth_methods: ("api_key" | "oauth" | "none")[];
  api_key_help: string | null;
  needs_local_runtime: boolean;
  oauth_supported: boolean;
}

interface VoiceInfo {
  id: string;
  label: string;
  gender: string;
  quality: string;
  installed: boolean;
  is_default: boolean;
  download_url: string | null;
  config_url: string | null;
}

// ---- Component -------------------------------------------------------------
export default function SettingsPage() {
  const refreshStatus = useSettingsStore((s) => s.refresh);
  const overall = useSettingsStore((s) => s.status);

  const [thm, setTHM] = useState<THMStatus | null>(null);
  const [thmEmail, setThmEmail] = useState("");
  const [thmPass, setThmPass] = useState("");
  const [thmCookie, setThmCookie] = useState("");
  const [thmCookieMode, setThmCookieMode] = useState(false);
  const [browserLoginJobId, setBrowserLoginJobId] = useState<string | null>(null);
  const [browserLoginStatus, setBrowserLoginStatus] = useState<"idle" | "pending" | "done" | "error">("idle");
  const [browserLoginError, setBrowserLoginError] = useState<string | null>(null);

  const [presets, setPresets] = useState<Preset[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [addingKind, setAddingKind] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function loadAll() {
    const [t, pr, p] = await Promise.all([
      api<THMStatus>("/api/settings/thm"),
      api<Preset[]>("/api/settings/providers/presets"),
      api<Provider[]>("/api/settings/providers"),
    ]);
    setTHM(t);
    setPresets(pr);
    setProviders(p);
  }

  useEffect(() => {
    loadAll().catch((e) => setErr((e as Error).message));
  }, []);

  async function saveTHM(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api("/api/settings/thm", {
        method: "PUT",
        body: JSON.stringify({ email: thmEmail, password: thmPass }),
      });
      setThmPass("");
      await loadAll();
      await refreshStatus();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteTHM() {
    await api("/api/settings/thm", { method: "DELETE" });
    await loadAll();
    await refreshStatus();
  }

  async function saveTHMCookies(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const raw = thmCookie.trim();
      let body: Record<string, unknown>;
      if (raw.startsWith("[") || raw.startsWith("{")) {
        // JSON: array of cookies or a single cookie object
        const parsed = JSON.parse(raw);
        body = { cookies: Array.isArray(parsed) ? parsed : [parsed] };
      } else if (raw.includes(";") || /^[\w\-\.]+=[^=]/.test(raw)) {
        // Multiple cookies (has ;) OR explicit name=value pattern (e.g. connect.sid=s%3A...)
        body = { cookie_header: raw };
      } else {
        // Plain value — treat as connect.sid (may contain = from base64 padding)
        body = { connect_sid: raw };
      }
      await api("/api/thm/session-cookies", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setThmCookie("");
      setThmCookieMode(false);
      await loadAll();
      await refreshStatus();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startBrowserLogin() {
    setBrowserLoginStatus("pending");
    setBrowserLoginError(null);
    try {
      const { job_id } = await api<{ job_id: string }>("/api/thm/browser-login/start", { method: "POST" });
      setBrowserLoginJobId(job_id);
      // Poll every 2 seconds
      const poll = setInterval(async () => {
        try {
          const res = await api<{ status: string; error: string | null }>(
            `/api/thm/browser-login/status/${job_id}`
          );
          if (res.status === "done") {
            clearInterval(poll);
            setBrowserLoginStatus("done");
            setBrowserLoginJobId(null);
            await loadAll();
            await refreshStatus();
          } else if (res.status === "error") {
            clearInterval(poll);
            setBrowserLoginStatus("error");
            setBrowserLoginError(res.error ?? "Erreur inconnue");
            setBrowserLoginJobId(null);
          }
        } catch {
          clearInterval(poll);
          setBrowserLoginStatus("error");
          setBrowserLoginError("Impossible de vérifier le statut.");
        }
      }, 2000);
    } catch (e) {
      setBrowserLoginStatus("error");
      setBrowserLoginError((e as Error).message);
    }
  }

  async function cancelBrowserLogin() {
    if (browserLoginJobId) {
      await api(`/api/thm/browser-login/${browserLoginJobId}`, { method: "DELETE" }).catch(() => {});
    }
    setBrowserLoginJobId(null);
    setBrowserLoginStatus("idle");
    setBrowserLoginError(null);
  }

  async function deleteProvider(id: number) {
    await api(`/api/settings/providers/${id}`, { method: "DELETE" });
    await loadAll();
    await refreshStatus();
  }

  async function setDefault(id: number) {
    await api(`/api/settings/providers/${id}/default`, { method: "POST" });
    await loadAll();
  }

  function connectGitHub(providerId: number) {
    window.open(
      apiUrl(`/api/oauth/github/start?provider_id=${providerId}`),
      "_blank",
      "width=600,height=700"
    );
  }

  return (
    <section className="space-y-6 max-w-5xl mx-auto">
      <header className="rounded-2xl border border-line bg-gradient-to-br from-violet-500/10 via-bg-2/40 to-bg-1/20 p-5 sm:p-6">
        <div className="flex items-center gap-4">
          <div className="grid place-items-center w-12 h-12 rounded-2xl bg-violet-500/20 ring-1 ring-violet-400/30 text-violet-300">
            <CogIcon className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-semibold text-slate-50">
              Paramètres
            </h1>
            <p className="text-sm text-slate-400 mt-0.5 flex items-center gap-1.5">
              <ShieldIcon className="w-3.5 h-3.5" /> Tout est stocké localement et
              chiffré (AES-256-GCM).
            </p>
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

      <SectionCard
        accent="emerald"
        icon={<CheckIcon className="w-5 h-5" />}
        title="État global"
        subtitle="Aperçu rapide de la configuration."
      >
        <ul className="space-y-2 text-sm">
          {overall && (
            <>
              <StatusRow label="TryHackMe" ok={overall.thm.ok} msg={overall.thm.message} />
              <StatusRow label="Providers IA" ok={overall.providers.ok} msg={overall.providers.message} />
              <StatusRow label="Modèles locaux" ok={overall.local_models.ok} msg={overall.local_models.message} />
            </>
          )}
        </ul>
      </SectionCard>

      <SectionCard
        accent="indigo"
        icon={<ShieldIcon className="w-5 h-5" />}
        title="TryHackMe"
        subtitle="Identifiants utilisés pour scraper les salles."
      >
        {thm?.configured ? (
          <div className="flex items-center justify-between text-sm">
            <div>
              Connecté en tant que{" "}
              <span className="font-mono text-violet-400">{thm.email_masked}</span>
              {thm.session_valid && <span className="badge-ok ml-2">session valide</span>}
            </div>
            <button className="btn-danger" onClick={deleteTHM} disabled={busy}>
              <TrashIcon /> Supprimer
            </button>
          </div>
        ) : (
          <>
            <form onSubmit={saveTHM} className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="label">Email</label>
                <input
                  type="email"
                  className="input"
                  required
                  value={thmEmail}
                  onChange={(e) => setThmEmail(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Mot de passe</label>
                <input
                  type="password"
                  className="input"
                  required
                  value={thmPass}
                  onChange={(e) => setThmPass(e.target.value)}
                />
              </div>
              <div className="sm:col-span-2">
                <button className="btn-primary" disabled={busy}>
                  <SaveIcon /> Enregistrer
                </button>
              </div>
            </form>

            <div className="mt-6 rounded-xl border border-line bg-bg-2/40 p-4 text-sm space-y-3">
              <p className="font-medium text-slate-200">
                CAPTCHA bloque la connexion ?
              </p>
              <p className="text-slate-400 text-xs">
                Clique sur le bouton ci-dessous : un navigateur s&apos;ouvre sur la
                page de connexion TryHackMe. Connecte-toi normalement (résous le
                CAPTCHA si besoin). Une fois connecté, le navigateur se ferme
                automatiquement et tes cookies sont importés.
              </p>

              {browserLoginStatus === "idle" && (
                <button className="btn-primary" onClick={startBrowserLogin}>
                  Ouvrir le navigateur et se connecter
                </button>
              )}

              {browserLoginStatus === "pending" && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-violet-400">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                    </svg>
                    <span>Navigateur ouvert — connecte-toi puis reviens ici…</span>
                  </div>
                  <button className="text-xs text-slate-400 underline" onClick={cancelBrowserLogin}>
                    Annuler
                  </button>
                </div>
              )}

              {browserLoginStatus === "done" && (
                <p className="text-green-400 text-xs font-medium">✓ Connexion réussie — cookies importés.</p>
              )}

              {browserLoginStatus === "error" && (
                <div className="space-y-2">
                  <p className="text-red-400 text-xs">{browserLoginError}</p>
                  <button className="btn-primary text-xs" onClick={() => { setBrowserLoginStatus("idle"); setBrowserLoginError(null); }}>
                    Réessayer
                  </button>
                </div>
              )}

              <details
                className="pt-2 border-t border-line"
                open={thmCookieMode}
                onToggle={(e) => setThmCookieMode((e.target as HTMLDetailsElement).open)}
              >
                <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">
                  Importer les cookies manuellement (fallback)
                </summary>
                <div className="mt-3 space-y-3">
                  <div className="rounded bg-bg-1 border border-line p-3">
                    <p className="text-xs text-slate-400 mb-1">F12 → Console sur tryhackme.com (connecté) → colle :</p>
                    <pre className="text-xs text-green-400 whitespace-pre-wrap break-all select-all">{`copy(JSON.stringify(document.cookie.split('; ').map(c => { const [n,...v]=c.split('='); return {name:n,value:v.join('='),domain:'.tryhackme.com',path:'/'}; })))`}</pre>
                  </div>
                  <form onSubmit={saveTHMCookies} className="space-y-2">
                    <textarea
                      className="input font-mono text-xs"
                      rows={4}
                      placeholder='[{"name":"connect.sid","value":"s%3A...","domain":".tryhackme.com","path":"/"}, ...]'
                      value={thmCookie}
                      onChange={(e) => setThmCookie(e.target.value)}
                      required
                    />
                    <div className="flex justify-end">
                      <button className="btn-primary text-xs" disabled={busy || !thmCookie.trim()}>
                        Importer
                      </button>
                    </div>
                  </form>
                </div>
              </details>
            </div>
          </>
        )}
      </SectionCard>

      <SectionCard
        accent="violet"
        icon={<KeyIcon className="w-5 h-5" />}
        title="Providers IA"
        subtitle="Connecte un ou plusieurs modèles. Le défaut est utilisé pour les réécritures."
      >
        <ul className="space-y-2 mb-6">
          {providers.map((p) => (
            <ProviderRow
              key={p.id}
              provider={p}
              onDefault={() => setDefault(p.id)}
              onDelete={() => deleteProvider(p.id)}
              onConnectGitHub={() => connectGitHub(p.id)}
              onChanged={loadAll}
            />
          ))}
          {providers.length === 0 && (
            <li className="text-sm text-slate-400 italic">Aucun provider configuré.</li>
          )}
        </ul>

        {addingKind === null ? (
          <div>
            <div className="text-sm text-slate-300 mb-3 flex items-center gap-2">
              <PlusIcon className="w-4 h-4" /> Ajouter un provider :
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {presets.map((p) => (
                <button
                  key={p.kind}
                  onClick={() => setAddingKind(p.kind)}
                  className="text-left rounded-xl border border-line hover:border-violet-400/40 bg-bg-2/40 hover:bg-bg-2/70 transition-all p-4 group"
                >
                  <div className="font-medium flex items-center gap-2 group-hover:text-violet-300">
                    {p.kind === "github_copilot" || p.kind === "github_models" ? (
                      <GitHubIcon className="w-4 h-4" />
                    ) : (
                      <KeyIcon className="w-4 h-4" />
                    )}
                    {p.label}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">{p.description}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <AddProviderForm
            preset={presets.find((p) => p.kind === addingKind)!}
            existingCount={providers.length}
            onCancel={() => setAddingKind(null)}
            onDone={async (newId, openOAuth) => {
              setAddingKind(null);
              await loadAll();
              await refreshStatus();
              if (openOAuth && newId !== null) connectGitHub(newId);
            }}
            onError={setErr}
          />
        )}
      </SectionCard>

      <VoiceSection onError={setErr} />
    </section>
  );
}

// ---- Add provider form (one preset at a time) ------------------------------
function AddProviderForm({
  preset,
  existingCount,
  onCancel,
  onDone,
  onError,
}: {
  preset: Preset;
  existingCount: number;
  onCancel: () => void;
  onDone: (newId: number | null, openOAuth: boolean) => void | Promise<void>;
  onError: (e: string) => void;
}) {
  const initialAuth: "api_key" | "oauth" | "none" =
    preset.oauth_supported && preset.auth_methods.includes("oauth")
      ? "oauth"
      : preset.auth_methods[0];

  const [auth, setAuth] = useState<"api_key" | "oauth" | "none">(initialAuth);
  const [apiKey, setApiKey] = useState("");
  const [advanced, setAdvanced] = useState(preset.kind === "custom");
  const [model, setModel] = useState(preset.default_model);
  const [baseUrl, setBaseUrl] = useState(preset.default_base_url ?? "");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        kind: preset.kind,
        auth_method: auth,
        is_default: existingCount === 0,
      };
      if (model && model !== preset.default_model) body.model = model;
      if (baseUrl && baseUrl !== (preset.default_base_url ?? "")) body.base_url = baseUrl;
      if (auth === "api_key" && apiKey) body.api_key = apiKey;

      const created = await api<Provider>("/api/settings/providers", {
        method: "POST",
        body: JSON.stringify(body),
      });

      if (auth === "oauth" && apiKey.trim()) {
        // user pasted a PAT instead of doing the OAuth dance
        await api(`/api/settings/providers/${created.id}/api_key`, {
          method: "PUT",
          body: JSON.stringify({ api_key: apiKey.trim() }),
        });
        onDone(created.id, false);
      } else {
        onDone(created.id, auth === "oauth" && !apiKey.trim());
      }
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-line bg-bg-2/40 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">{preset.label}</div>
          <div className="text-xs text-slate-400">{preset.description}</div>
        </div>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          Annuler
        </button>
      </div>

      {preset.auth_methods.length > 1 && (
        <div>
          <label className="label">Méthode d'authentification</label>
          <div className="flex flex-wrap gap-2">
            {preset.auth_methods.map((m) => (
              <button
                type="button"
                key={m}
                onClick={() => setAuth(m)}
                className={`btn ${auth === m ? "bg-violet-500 text-white" : "btn-ghost"}`}
              >
                {m === "oauth"
                  ? preset.oauth_supported
                    ? "OAuth"
                    : "OAuth (non configuré)"
                  : m === "api_key"
                    ? "Clé API / PAT"
                    : "Aucune"}
              </button>
            ))}
          </div>
        </div>
      )}

      {auth === "api_key" && (
        <div>
          <label className="label">Clé API</label>
          <input
            type="password"
            className="input"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            required
          />
          {preset.api_key_help && (
            <div className="text-xs text-slate-500 mt-1">
              Obtiens une clé :{" "}
              <a
                href={preset.api_key_help.startsWith("http") ? preset.api_key_help : "#"}
                target="_blank"
                rel="noreferrer"
                className="text-violet-400 underline"
              >
                {preset.api_key_help}
              </a>
            </div>
          )}
        </div>
      )}

      {auth === "oauth" && (
        <div className="rounded-lg border border-line bg-bg-1/60 p-3 text-sm text-slate-300 space-y-2">
          {preset.oauth_supported ? (
            <p>
              Le provider sera créé puis une fenêtre GitHub s'ouvrira pour
              autoriser l'accès. Fonctionne aussi en localhost.
            </p>
          ) : (
            <p className="text-amber-300">
              OAuth GitHub n'est pas configuré côté serveur. Renseigne{" "}
              <code className="mx-1 px-1 rounded bg-bg-2">GITHUB_OAUTH_CLIENT_ID</code>{" "}
              et{" "}
              <code className="mx-1 px-1 rounded bg-bg-2">GITHUB_OAUTH_CLIENT_SECRET</code>{" "}
              dans <code>.env</code>, ou colle un Personal Access Token ci-dessous.
            </p>
          )}
          <label className="label">Ou colle un Personal Access Token (facultatif)</label>
          <input
            type="password"
            className="input"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="github_pat_..."
          />
          {preset.api_key_help && (
            <div className="text-xs text-slate-500">{preset.api_key_help}</div>
          )}
        </div>
      )}

      {auth === "none" && preset.needs_local_runtime && (
        <div className="rounded-lg border border-line bg-bg-1/60 p-3 text-sm text-slate-300">
          Assure-toi que <code>{preset.label}</code> tourne localement. URL :{" "}
          <code className="text-violet-400">{preset.default_base_url}</code>
        </div>
      )}

      <div>
        <label className="label">Modèle</label>
        <input
          className="input"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={preset.default_model}
        />
        <div className="text-xs text-slate-500 mt-1">
          Par défaut : <code>{preset.default_model}</code>. Tu pourras le
          changer plus tard. Une fois la clé renseignée, une liste des modèles
          disponibles s'affichera dans les paramètres du provider.
        </div>
      </div>

      <details
        open={advanced}
        onToggle={(e) => setAdvanced((e.target as HTMLDetailsElement).open)}
      >
        <summary className="text-xs text-slate-400 cursor-pointer select-none">
          Avancé (URL personnalisée)
        </summary>
        <div className="mt-3">
          <label className="label">Base URL</label>
          <input
            className="input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={preset.default_base_url ?? "(par défaut)"}
          />
        </div>
      </details>

      <div className="flex justify-end">
        <button className="btn-primary" disabled={busy}>
          {busy ? "Ajout…" : "Ajouter"}
        </button>
      </div>
    </form>
  );
}

function StatusRow({ label, ok, msg }: { label: string; ok: boolean; msg: string }) {
  return (
    <li className="flex items-center justify-between border-b border-line py-2 last:border-0">
      <span>{label}</span>
      <span className={ok ? "badge-ok" : "badge-err"}>
        {ok ? "✓ " : "✗ "}
        {msg}
      </span>
    </li>
  );
}

// ---- Provider row (with inline model editor + model listing) -------------
function ProviderRow({
  provider,
  onDefault,
  onDelete,
  onConnectGitHub,
  onChanged,
}: {
  provider: Provider;
  onDefault: () => void | Promise<void>;
  onDelete: () => void | Promise<void>;
  onConnectGitHub: () => void;
  onChanged: () => void | Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [model, setModel] = useState(provider.model);
  const [models, setModels] = useState<string[] | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

  async function loadModels() {
    setLoadingModels(true);
    try {
      const list = await api<string[]>(
        `/api/settings/providers/${provider.id}/models`
      );
      setModels(list);
    } catch {
      setModels([]);
    } finally {
      setLoadingModels(false);
    }
  }

  async function save() {
    if (!model.trim() || model === provider.model) {
      setEditing(false);
      return;
    }
    setBusy(true);
    setLocalErr(null);
    try {
      await api(`/api/settings/providers/${provider.id}/model`, {
        method: "PUT",
        body: JSON.stringify({ model: model.trim() }),
      });
      setEditing(false);
      await onChanged();
    } catch (e) {
      setLocalErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-xl border border-line bg-bg-2/40 px-4 py-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          <div className="font-medium flex items-center gap-2">
            {provider.name}
            {provider.is_default && <span className="badge-ok">défaut</span>}
            {provider.has_credentials ? (
              <span className="badge-ok">✓ creds</span>
            ) : (
              <span className="badge-warn">⚠ creds manquantes</span>
            )}
          </div>
          {!editing && (
            <button
              type="button"
              className="text-slate-400 text-xs hover:text-violet-400 transition-colors"
              onClick={() => {
                setEditing(true);
                if (models === null) loadModels();
              }}
              title="Modifier le modèle"
            >
              {provider.model} ✎
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!provider.is_default && (
            <button className="btn-ghost" onClick={onDefault}>
              Par défaut
            </button>
          )}
          {provider.kind === "github_models" &&
            provider.auth_method === "oauth" && (
              <button className="btn-ghost" onClick={onConnectGitHub}>
                Connecter GitHub
              </button>
            )}
          <button className="btn-danger" onClick={onDelete}>
            Supprimer
          </button>
        </div>
      </div>

      {editing && (
        <div className="space-y-2">
          {loadingModels ? (
            <div className="text-xs text-slate-500">
              Chargement des modèles disponibles…
            </div>
          ) : models && models.length > 0 ? (
            <select
              className="input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {!models.includes(model) && (
                <option value={model}>{model} (actuel)</option>
              )}
              {models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Nom du modèle"
            />
          )}
          {models && models.length === 0 && !loadingModels && (
            <div className="text-xs text-slate-500">
              Liste des modèles non disponible pour ce provider — saisis le
              nom manuellement.
            </div>
          )}
          {localErr && (
            <div className="text-xs text-rose-300">{localErr}</div>
          )}
          <div className="flex gap-2 justify-end">
            <button
              className="btn-ghost"
              onClick={() => {
                setEditing(false);
                setModel(provider.model);
              }}
              disabled={busy}
            >
              Annuler
            </button>
            <button className="btn-primary" onClick={save} disabled={busy}>
              {busy ? "…" : "Enregistrer"}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}


/* ----------------------- Voice / TTS section --------------------------- */
function VoiceSection({ onError }: { onError: (e: string) => void }) {
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [installing, setInstalling] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const list = await api<VoiceInfo[]>(/api/voice/voices);
      setVoices(list);
    } catch (e) {
      onError((e as Error).message);
    }
  }
  useEffect(() => { load(); }, []);

  async function setDefault(id: string) {
    setSaving(true);
    try {
      await api(/api/voice/voices/default, {
        method: "PUT",
        body: JSON.stringify({ voice_id: id }),
      });
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function install(v: VoiceInfo) {
    if (!v.download_url) return;
    setInstalling(v.id);
    try {
      await api(/api/voice/voices/install, {
        method: "POST",
        body: JSON.stringify({ voice_id: v.id }),
      });
      await load();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setInstalling(null);
    }
  }

  async function preview(id: string) {
    try {
      const resp = await fetch(apiUrl(/api/voice/tts), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: "Bonjour, je suis votre nouvelle voix pour la lecture des cours.",
          voice: id,
        }),
      });
      if (!resp.ok) throw new Error(TTS );
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play();
      audio.onended = () => URL.revokeObjectURL(url);
    } catch (e) {
      onError("Aper�u impossible : " + (e as Error).message);
    }
  }

  return (
    <SectionCard
      accent="emerald"
      icon={<VoiceIcon className="w-5 h-5" />}
      title="Voix de lecture (TTS)"
      subtitle="Choisis la voix fran�aise utilis�e par Piper pour lire les cours."
    >
      <ul className="space-y-2">
        {voices.map((v) => (
          <li
            key={v.id}
            className={
              "rounded-xl border px-4 py-3 flex flex-wrap items-center justify-between gap-3 transition-colors " +
              (v.is_default
                ? "bg-violet-500/10 border-violet-400/40"
                : "bg-bg-2/40 border-line hover:border-violet-400/30")
            }
          >
            <div className="min-w-0">
              <div className="font-medium flex items-center gap-2 text-slate-100">
                <span className="text-lg leading-none">
                  {v.gender === "male" ? "?" : v.gender === "female" ? "?" : "�"}
                </span>
                {v.label}
                {v.is_default && <span className="badge-ok">d�faut</span>}
                {!v.installed && (
                  <span className="text-xs text-amber-300 bg-amber-500/10 border border-amber-400/30 rounded-full px-2 py-0.5">
                    � t�l�charger
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500 font-mono">
                {v.id} � qualit� {v.quality}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {v.installed ? (
                <>
                  <button
                    className="btn-ghost text-xs"
                    onClick={() => preview(v.id)}
                    title="�couter un aper�u"
                  >
                    Aper�u
                  </button>
                  {!v.is_default && (
                    <button
                      className="btn-primary text-xs"
                      onClick={() => setDefault(v.id)}
                      disabled={saving}
                    >
                      <CheckIcon /> Choisir
                    </button>
                  )}
                </>
              ) : (
                <button
                  className="btn-primary text-xs"
                  onClick={() => install(v)}
                  disabled={installing === v.id}
                >
                  <DownloadIcon />
                  {installing === v.id ? "Installation�" : "Installer"}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500 mt-3 flex items-center gap-1.5">
        <RefreshIcon className="w-3 h-3" />
        Les mod�les sont t�l�charg�s depuis Hugging Face dans models/piper.
      </p>
    </SectionCard>
  );
}