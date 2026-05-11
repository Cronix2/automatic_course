# Architecture

## Vue d'ensemble

```txt
┌──────────────────────────────────────────────────────────────────┐
│                          Browser (React)                         │
│  Pages: Home / Settings / Courses / Player                       │
│  - Settings gate: bloque l'app tant que la config est incomplète │
│  - Player: streaming texte + audio + micro (push-to-talk)        │
└────────────────┬─────────────────────────────────────────────────┘
                 │ HTTPS / fetch streaming (SSE-like)
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI async)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────┐   │
│  │ Settings API    │  │ AI orchestrator │  │ Voice API (STT/TTS)│   │
│  │  /api/settings  │  │  /api/ai/*      │  │  /api/voice/*      │   │
│  └────────┬────────┘  └────────┬────────┘  └─────────┬──────────┘   │
│           │                    │                     │              │
│           ▼                    ▼                     ▼              │
│  ┌─────────────────┐  ┌────────────────┐  ┌────────────────────┐    │
│  │ Secrets service │  │ Provider       │  │ STT: faster-whisper│    │
│  │ (AES-256-GCM)   │  │ registry       │  │ TTS: Piper         │    │
│  └────────┬────────┘  └───┬────────────┘  └────────────────────┘    │
│           ▼               ▼                                         │
│  ┌─────────────────┐  ┌────────────────┐                            │
│  │ SQLite          │  │ OpenAI-compat  │                            │
│  │  - secrets      │  │ Anthropic      │                            │
│  │  - providers    │  │ Ollama         │                            │
│  │  - settings     │  │ GitHub Models  │                            │
│  └─────────────────┘  └────────┬───────┘                            │
│                                 │                                   │
│  ┌─────────────────────────────┴──────────┐                         │
│  │ THM client (Playwright headless)       │                         │
│  └────────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Flux principal (lecture d'un cours)

1. `POST /api/thm/fetch { room_code }` → Playwright restaure la session, va chercher la page, extrait le texte.
2. `POST /api/ai/enhance { content, provider_id, style }` → streaming texte via le provider IA configuré.
3. Le frontend accumule le texte, puis :
4. `GET /api/voice/tts?text=…` → renvoie un WAV synthétisé par Piper, joué dans `<audio>`.
5. À tout moment, l'utilisateur peut :
   - cliquer **Interrompre** → `audio.pause()`
   - cliquer **🎙 Parler** → MediaRecorder → `POST /api/voice/stt` → texte → `/api/ai/chat` (streaming) → TTS.

## Persistance & chiffrement

- **DB** : SQLite (`aiosqlite`), un seul fichier dans `data/app.db` (volume Docker monté).
- **Secrets** (table `secrets`) : chiffrés AES-256-GCM, **associated_data = clé du secret** pour empêcher la substitution croisée.
- **Clé maître** : `APP_MASTER_KEY` (32 octets base64), uniquement dans `.env`, jamais en DB ni en code.

## Choix techniques justifiés

| Décision | Raison |
| --- | --- |
| FastAPI | Async natif (streaming SSE pour le LLM), typage Pydantic, doc OpenAPI gratuite. |
| SQLite | Mono-utilisateur, zéro infra, simple à sauvegarder (1 fichier). |
| faster-whisper (CTranslate2) | 4–10× plus rapide que `openai/whisper`, int8 sur CPU, qualité équivalente. |
| Piper | Latence sub-100 ms, < 100 MB par voix, multi-langues, ONNX (pas de CUDA requis). |
| Playwright Chromium | Le seul moyen fiable de scraper THM (JS rendering, anti-bot léger). |
| OpenAI-compatible adapter | OpenRouter / OpenAI / GitHub Models / Ollama exposent quasi le même JSON. Un seul code à maintenir. |
| Tailwind + zustand | Vélocité de dev, bundle léger, pas de boilerplate Redux. |

## Limites connues / Roadmap

- Pas encore de listing des rooms souscrites (on saisit le `room_code` manuellement).
- Wake-word non encore branché (UI prête, hook à créer côté `useWakeWord`).
- Multi-utilisateurs non supporté (par design : usage local).
- Streaming TTS au niveau "phrase" : actuellement on synthétise puis on découpe ; pour < 100 ms de latence il faut tokeniser et appeler Piper phrase par phrase.
