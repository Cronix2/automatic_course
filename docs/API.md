# API REST

Base URL : `http://localhost:8001`

OpenAPI interactif : `http://localhost:8001/docs` (uniquement en dev).

## Conventions

- Toutes les routes retournent du JSON sauf mention contraire.
- Streaming texte : `Content-Type: text/plain; charset=utf-8`, chunks UTF-8 bruts (à concaténer côté client).
- Streaming audio : `audio/wav` (complet) ou `application/octet-stream` (PCM brut 16 bits mono).

## `GET /api/health`

Healthcheck. Retourne `{"status":"ok"}`.

## Settings

### `GET /api/settings/status`

État global des trois catégories (THM / providers / modèles locaux). Utilisé par la garde UI.

```json
{
  "thm": { "ok": true,  "message": "OK" },
  "providers": { "ok": true, "message": "OK" },
  "local_models": { "ok": true, "message": "Configured." },
  "overall_ok": true
}
```

### TryHackMe credentials

- `GET    /api/settings/thm` → `{ configured, session_valid, email_masked }`
- `PUT    /api/settings/thm` body: `{ email, password }`
- `DELETE /api/settings/thm`

### Providers

- `GET    /api/settings/providers/kinds` → liste des kinds supportés
- `GET    /api/settings/providers`
- `POST   /api/settings/providers` body: `{ name, kind, model, base_url?, auth_method, api_key?, is_default? }`
- `DELETE /api/settings/providers/{id}`

## TryHackMe

- `POST /api/thm/login` — force un login si la session est invalide.
- `POST /api/thm/fetch` body: `{ room_code }` → `CourseContent`.

## AI (streaming texte)

- `POST /api/ai/enhance` body: `{ content, provider_id, style }`
- `POST /api/ai/chat` body: `{ provider_id, messages, stream }`

Réponse : flux texte (à lire avec `ReadableStream` côté JS, voir `frontend/src/api/client.ts::streamText`).

## Voice

- `POST /api/voice/stt` — multipart, champs : `audio` (file), `language` (default `fr`). Retourne `{ text }`.
- `GET  /api/voice/tts?text=…&voice=…` → `audio/wav`.
- `GET  /api/voice/tts/stream?text=…&voice=…` → PCM 16-bit mono streamé.

## OAuth GitHub

- `GET /api/oauth/github/start?provider_id=<id>` → redirige vers GitHub.
- `GET /api/oauth/github/callback?code=…&state=…` → stocke le token chiffré, ferme la popup.
