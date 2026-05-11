<div align="center">

# 🎧 Automatic Course

**Transforme un cours TryHackMe en cours audio amélioré par IA, interruptible à la voix.**

[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)
![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%2FVite-6d28d9.svg)
![STT](https://img.shields.io/badge/STT-faster--whisper-1e40af.svg)
![TTS](https://img.shields.io/badge/TTS-Piper-1e40af.svg)

</div>

---

## ✨ Vue d'ensemble

`automatic_course` est une application web auto-hébergée qui :

1. 🔐 Se connecte à **TryHackMe** avec tes credentials (stockés chiffrés en local).
2. 📚 Te laisse sélectionner un cours / une room / une task.
3. 🧠 Récupère le texte de la page et le **réécrit** via un modèle IA (concis, plus profond techniquement).
4. 🗣️ Lit le résultat **en vocal** (TTS local, faible latence).
5. 🎙️ Te permet d'**interrompre l'IA** à la voix ou au clavier pour poser une question / demander un développement / une définition.
6. ⚙️ Supporte **plusieurs fournisseurs IA** (OpenRouter, GitHub Models, OpenAI, Anthropic, Ollama local).

> **STT et TTS tournent 100 % en local** (faster-whisper + Piper) — aucune fuite audio vers un cloud.

---

## 🧱 Stack

| Composant       | Choix                                                  |
| --------------- | ------------------------------------------------------ |
| Backend         | FastAPI (Python 3.11+, async)                          |
| Frontend        | React 18 + Vite + TypeScript + Tailwind                |
| DB              | SQLite (`aiosqlite`) + chiffrement AES-GCM des secrets |
| STT             | `faster-whisper` (CTranslate2)                         |
| TTS             | `piper-tts` (ONNX, ultra rapide)                       |
| Scraping THM    | Playwright headless                                    |
| Auth providers  | OAuth GitHub + API keys chiffrées                      |
| Déploiement     | Docker Compose                                         |

---

## 🚀 Démarrage rapide

### Prérequis

- **Docker** + **Docker Compose v2** (recommandé)
- *ou* Python 3.11+, Node 20+, pour le mode dev local

### Déploiement automatique (Docker)

```powershell
# Windows
.\deploy.ps1
```

```bash
# Linux / macOS
chmod +x deploy.sh
./deploy.sh
```

Le script :

- vérifie les pré-requis (Docker, ports libres),
- crée un `.env` depuis `.env.example` si absent,
- génère automatiquement `APP_MASTER_KEY` et `SESSION_SECRET`,
- télécharge les modèles Whisper/Piper si manquants,
- build et lance les containers.

Une fois prêt : ouvre **<http://localhost:5173>**.

Mode dev manuel : voir [docs/SETUP.md](docs/SETUP.md).

---

## ⚙️ Configuration — page Settings

Au premier lancement, l'app **bloque** tout l'usage tant que les paramètres requis ne sont pas valides. La page **Settings** affiche pour chaque catégorie un statut clair (`✓ OK`, `⚠ manquant`, `✗ invalide`).

Catégories :

1. **TryHackMe** : email + mot de passe (login Playwright, cookie chiffré).
2. **Providers IA** : 1..N entrées (provider + modèle + auth).
3. **STT/TTS local** : modèle Whisper, voix Piper, langue.
4. **Wake-word & interruption** : sensibilité, mot-clé.

Aucune clé n'est stockée en clair : AES-256-GCM avec clé maître via `APP_MASTER_KEY`.

---

## 🔐 Sécurité

- ❌ Zéro secret en dur dans le code.
- 🔑 Secrets chiffrés AES-256-GCM au repos.
- 🍪 Sessions signées (HMAC), cookies `HttpOnly` + `SameSite=Lax`.
- 🛡️ Protection CSRF (double-submit token) sur mutations.
- 🚧 CORS strict, CSP, HSTS, X-Frame-Options.
- 🧯 Rate-limit sur login, OAuth, IA.
- 📜 Audit log local.

Détails : [docs/SECURITY.md](docs/SECURITY.md).

---

## 🧠 Providers IA

| Provider           | Auth                       | Streaming |
| ------------------ | -------------------------- | --------- |
| OpenRouter         | API key                    | ✅        |
| GitHub Models      | **OAuth GitHub** ou PAT    | ✅        |
| OpenAI             | API key                    | ✅        |
| Anthropic          | API key                    | ✅        |
| Ollama (local)     | URL locale                 | ✅        |

Ajouter un provider : voir [docs/PROVIDERS.md](docs/PROVIDERS.md).

---

## 🗣️ STT & TTS locaux

- **STT → `faster-whisper`** (CTranslate2, 4–10× plus rapide que `openai/whisper`, int8 sur CPU).
- **TTS → Piper** (ONNX, < 100 ms / phrase, streaming PCM, ~30 voix FR/EN).

Alternatives prêtes à brancher : Coqui XTTS v2 (qualité ++ mais lent), Kokoro-TTS.

---

## 🎙️ Interruption

1. Bouton **Interrompre**.
2. **Push-to-talk** (`Espace`).
3. **Wake-word** configurable (Porcupine ou détecteur custom).

---

## 📂 Structure

```txt
automatic_course/
├── backend/                 # FastAPI app
│   ├── app/
│   │   ├── api/             # routes HTTP / WebSocket
│   │   ├── services/        # providers IA, THM, STT, TTS
│   │   ├── db/              # SQLAlchemy async
│   │   ├── security/        # crypto AES-GCM
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # React + Vite + Tailwind
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── hooks/
│   └── Dockerfile
├── docs/
├── docker-compose.yml
├── deploy.ps1 / deploy.sh
└── .env.example
```

---

## 📚 Documentation

- [docs/SETUP.md](docs/SETUP.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/API.md](docs/API.md)
- [docs/PROVIDERS.md](docs/PROVIDERS.md)

---

## ⚖️ Légal

Automatise **uniquement ton propre compte** TryHackMe, dans la limite de leurs CGU. Tu es responsable de la conformité aux CGU des providers IA.

---

## 📝 Licence

MIT — voir [LICENSE](LICENSE).
