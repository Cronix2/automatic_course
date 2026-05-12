# Providers IA

## Providers supportés

| Kind             | Auth          | Modèles types                                  | Base URL par défaut                       |
| ---------------- | ------------- | ---------------------------------------------- | ----------------------------------------- |
| `openrouter`     | `api_key`     | `openai/gpt-4o-mini`, `anthropic/...`          | `https://openrouter.ai/api/v1`            |
| `openai`         | `api_key`     | `gpt-4o-mini`, `gpt-4.1`                       | `https://api.openai.com/v1`               |
| `anthropic`      | `api_key`     | `claude-3-5-sonnet-latest`                     | `https://api.anthropic.com/v1`            |
| `github_models`  | `oauth` / PAT | `openai/gpt-4o-mini`, `Meta-Llama-3.1`         | `https://models.inference.ai.azure.com`   |
| `github_copilot` | `oauth` / PAT | catalogue VS Code (Claude, Gemini, GPT, Grok…) | `https://api.githubcopilot.com` (interne) |
| `ollama`         | `none`        | `llama3.1`, `qwen2.5`, etc.                    | `http://localhost:11434/v1`               |

> `github_models` (Azure AI Inference) et `github_copilot` (Copilot Chat) sont **deux services distincts** malgré le nom proche. Copilot nécessite un abonnement actif.

## GitHub Copilot (non officiel)

L'intégration utilise le contrat utilisé par les extensions VS Code / neovim-copilot :

1. Token long terme : OAuth GitHub (ou PAT obtenu via `gh auth token` — pas un PAT classique des Developer Settings).
2. À chaque appel, on échange ce token contre un token Copilot court (~30 min) via `GET https://api.github.com/copilot_internal/v2/token`.
3. Chat : `POST https://api.githubcopilot.com/chat/completions` (format OpenAI, streaming SSE).
4. Catalogue de modèles : `GET https://api.githubcopilot.com/models` — récupéré dynamiquement, donc la liste affichée correspond exactement à ce que tu vois dans le sélecteur VS Code (Claude Sonnet 4.5, Gemini 2.5 Pro, GPT-5, Grok Code Fast 1, etc.).

Si tu vois `network error` au stream :

- Vérifie que ton compte a Copilot actif (`gh copilot status` ou interface GitHub).
- Clique **Rafraîchir les modèles** dans la page Réglages : ça force un appel `/models` qui remontera le vrai code d'erreur (401 = pas d'abo, 403 = abo expiré).

⚠ Endpoint non officiel : Microsoft peut le changer sans préavis.

## Ajouter un nouveau provider

1. Créer une classe dans `backend/app/services/providers/<mon_provider>.py` :

   ```python
   from .base import AIProvider, ChatTurn

   class MyProvider(AIProvider):
       kind = "my_provider"

       async def stream_chat(self, messages: list[ChatTurn]):
           yield "..."
   ```

2. L'enregistrer dans `registry.py` :

   ```python
   _REGISTRY["my_provider"] = MyProvider
   ```

3. Ajouter un `ProviderPreset` dans `presets.py` (label, default_model, auth_methods).
4. (Optionnel) Mettre à jour `frontend/src/pages/SettingsPage.tsx` pour des champs UI spécifiques.

## OAuth (GitHub Models / GitHub Copilot)

1. Crée une OAuth App sur [https://github.com/settings/developers](https://github.com/settings/developers).
2. Callback URL = `${PUBLIC_BASE_URL}/api/oauth/github/callback`.
3. Renseigne `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` dans `.env`.
4. Dans Réglages, ajoute un provider `github_models` ou `github_copilot` avec `auth_method=oauth`, puis clique **Connecter GitHub** → popup → token stocké chiffré.

## Tester un provider rapidement

```bash
curl -N -X POST http://localhost:8001/api/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "provider_id": 1,
    "messages": [{"role":"user","content":"dis bonjour"}],
    "stream": true
  }'
```
