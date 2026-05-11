# Providers IA

## Providers supportés (MVP)

| Kind            | Auth        | Modèles types                          | Base URL par défaut                        |
| --------------- | ----------- | -------------------------------------- | ------------------------------------------ |
| `openrouter`    | `api_key`   | `openai/gpt-4o-mini`, `anthropic/...`  | `https://openrouter.ai/api/v1`             |
| `openai`        | `api_key`   | `gpt-4o-mini`, `gpt-4.1`               | `https://api.openai.com/v1`                |
| `anthropic`     | `api_key`   | `claude-3-5-sonnet-latest`             | `https://api.anthropic.com/v1`             |
| `github_models` | `oauth`/PAT | `openai/gpt-4o-mini`, `Meta-Llama-3.1` | `https://models.inference.ai.azure.com`    |
| `ollama`        | `none`      | `llama3.1`, `qwen2.5`, etc.            | `http://localhost:11434/v1`                |

Tous les providers ci-dessus exposent la même API `/chat/completions` (OpenAI-compatible) ou l'API Messages d'Anthropic. Une seule classe générique gère les 4 premiers, Anthropic a sa propre classe.

## Ajouter un nouveau provider

1. Créer une classe dans `backend/app/services/providers/<mon_provider>.py` :

    ```python
    from .base import AIProvider, ChatTurn

    class MyProvider(AIProvider):
        kind = "my_provider"

        async def stream_chat(self, messages: list[ChatTurn]):
            # ... appeler l'API, yielder des tokens texte au fur et à mesure
            yield "..."
    ```

2. L'enregistrer dans `registry.py` :

    ```python
    _REGISTRY["my_provider"] = MyProvider
    ```

3. (Optionnel) Mettre à jour `frontend/src/pages/SettingsPage.tsx` si tu veux des champs UI spécifiques.

## OAuth (GitHub Models)

1. Crée une OAuth App sur <https://github.com/settings/developers>.
2. Callback URL = `${PUBLIC_BASE_URL}/api/oauth/github/callback`.
3. Renseigne `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` dans `.env`.
4. Dans la page Settings, ajoute un provider `github_models` avec `auth_method=oauth`, puis clique **Connecter GitHub** → popup → token stocké chiffré.

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
