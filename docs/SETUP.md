# Setup

## 1. Avec Docker (recommandé)

### Prérequis

- Docker Desktop (Windows / macOS) **ou** Docker Engine + plugin `compose` (Linux)
- Le port `5173` (frontend) et `8001` (backend) doivent être libres (configurables dans `.env`)

### Étapes

```powershell
# Windows
git clone https://github.com/Cronix2/automatic_course.git
cd automatic_course
.\deploy.ps1
```

```bash
# Linux / macOS
git clone https://github.com/Cronix2/automatic_course.git
cd automatic_course
chmod +x deploy.sh
./deploy.sh
```

Le script crée `.env` automatiquement et génère `APP_MASTER_KEY` (clé AES 256 bits) et `SESSION_SECRET`. Ouvre ensuite **<http://localhost:5173>**.

> 💡 **Si tu lances `docker compose up` directement sans passer par
> `deploy.sh`/`deploy.ps1`** et que `APP_MASTER_KEY` / `SESSION_SECRET` sont
> vides dans `.env`, le backend les **génère lui-même** au démarrage et les
> persiste dans `data/.bootstrap.env`. Sauvegarde ce fichier : sa perte
> empêchera de déchiffrer les credentials stockés.

### Commandes utiles

```bash
docker compose logs -f backend       # logs backend
docker compose logs -f frontend      # logs frontend
docker compose restart backend       # redémarrer
./deploy.sh down                     # tout arrêter
./deploy.sh rebuild                  # rebuild sans cache
```

---

## 2. Dev manuel

### Backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1            # PowerShell
# . .venv/bin/activate                  # bash
pip install -r requirements.txt
python -m playwright install chromium
cp ../.env.example ../.env
# édite ../.env : APP_MASTER_KEY + SESSION_SECRET (voir README)
uvicorn app.main:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Le proxy Vite redirige `/api/*` vers `http://localhost:8001`.

---

## 3. Modèles locaux

### faster-whisper

Téléchargement automatique à la première transcription dans `~/.cache/huggingface` (ou `data/whisper`). Modèle par défaut : `base`. Changer via `WHISPER_MODEL=small` dans `.env` pour plus de précision.

### Piper

Télécharge une voix depuis [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main) et copie les deux fichiers (`*.onnx` + `*.onnx.json`) dans `models/piper/`. Exemple pour le français :

```bash
mkdir -p models/piper
cd models/piper
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json
```

---

## 4. OAuth GitHub (optionnel)

Cette section est nécessaire **uniquement** si tu veux te connecter à GitHub
Models sans manipuler de Personal Access Token. Sinon, dans l'UI, choisis
« Clé API / PAT » et colle un token : ça marche tout aussi bien.

> ⚠️ **GitHub OAuth fonctionne sans HTTPS en localhost.** Inutile d'exposer
> ton instance ou de configurer un domaine. La seule contrainte : l'URL de
> callback doit correspondre **exactement** à ce que tu déclares à GitHub.

### 4.1 Créer l'application OAuth GitHub

1. Va sur <https://github.com/settings/developers> et choisis l'onglet
   **OAuth Apps** (pas « GitHub Apps », ce n'est pas le même produit).
2. Clique **New OAuth App**.
3. Remplis le formulaire :

   | Champ                          | Valeur recommandée                                |
   |--------------------------------|---------------------------------------------------|
   | **Application name**           | `Automatic Course (local)`                        |
   | **Homepage URL**               | `http://localhost:5173`                           |
   | **Application description**    | _facultatif_                                      |
   | **Authorization callback URL** | `http://localhost:8001/api/oauth/github/callback` |

   La callback URL doit correspondre **caractère pour caractère** à
   `${PUBLIC_BASE_URL}/api/oauth/github/callback`. Si tu changes
   `PUBLIC_BASE_URL` ou `BACKEND_PORT` dans `.env`, modifie-la ici aussi.

4. Clique **Register application**.

### 4.2 Récupérer les identifiants

1. Tu arrives sur la page de l'application. Note le **Client ID**.
2. Clique **Generate a new client secret**. Confirme avec ton mot de passe
   GitHub. Copie immédiatement le **Client Secret** : il ne sera plus
   affiché.

### 4.3 Configurer le backend

Édite `.env` à la racine du projet :

```ini
GITHUB_OAUTH_CLIENT_ID=Iv1.xxxxxxxxxxxxxxxx
GITHUB_OAUTH_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PUBLIC_BASE_URL=http://localhost:8001
```

Puis redémarre le backend :

```bash
docker compose up -d backend
```

### 4.4 Vérifier dans l'UI

1. Ouvre <http://localhost:5173/settings>.
2. Section **Providers IA** → **Ajouter un provider** → **GitHub Models**.
3. Si tout est OK, l'onglet **OAuth** s'affiche sans message d'avertissement.
   Sinon il indique que `GITHUB_OAUTH_CLIENT_ID` est manquant et propose le
   fallback PAT.
4. Clique **Ajouter** : une fenêtre GitHub s'ouvre, autorise l'app, et tu es
   redirigé vers une page de succès. Le provider apparaît avec le badge
   `✓ creds`.

### 4.5 Scopes demandés

Pour l'instant, l'app ne demande **aucun scope spécifique** (`scope=`).
Cela suffit pour appeler GitHub Models avec le token retourné. Si GitHub
modifie cette politique à l'avenir, ajoute `models:read` dans la config
OAuth de la route `routes_oauth.py`.

### 4.6 Dépannage

| Symptôme                        | Cause probable                 | Correction                                                                                                      |
|---------------------------------|--------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `redirect_uri_mismatch`         | Callback URL ne correspond pas | Recopier exactement la valeur dans GitHub                                                                       |
| Popup fermée sans rien          | Bloqueur de popup              | Autoriser les popups pour `localhost`                                                                           |
| `Bad verification code`         | Code OAuth réutilisé           | Refaire la connexion depuis l'UI                                                                                |
| OAuth marche mais 401 sur l'API | Token sans accès à Models      | Soit utiliser un PAT avec scope `models:read`, soit confirmer que ton compte a accès au programme GitHub Models |

### 4.7 Alternative : Personal Access Token

Si tu préfères contourner OAuth :

1. <https://github.com/settings/tokens> → **Generate new token (classic)**.
2. Coche le scope **`models:read`**.
3. Dans l'UI, choisis **GitHub Models** → onglet **Clé API / PAT** et colle
   le token. Aucune config dans `.env` n'est requise.

---

## 5. TryHackMe : contournement du CAPTCHA

TryHackMe protège son login avec un **reCAPTCHA Google** que Playwright (en
mode headless) ne peut pas résoudre — c'est volontaire de leur part, et le
contourner serait contraire à leurs CGU.

Si tu vois ce message dans l'UI :

> *TryHackMe demande un CAPTCHA — connexion automatique impossible._

tu as deux solutions propres :

### 5.1 Solution recommandée : importer un cookie de session

C'est rapide, ça fonctionne tant que ton cookie THM est valide (~30 jours)
et ça ne nécessite aucune configuration côté serveur.

1. Connecte-toi normalement sur <https://tryhackme.com/login> dans **ton
   navigateur**, en résolvant le CAPTCHA manuellement.
2. Une fois connecté, ouvre les DevTools (`F12`) → onglet **Application**
   (ou **Storage** sur Firefox) → **Cookies** → `https://tryhackme.com`.
3. Repère la ligne `connect.sid` et copie sa **valeur entière** (elle
   commence par `s%3A...`).
4. Dans Automatic Course → **Réglages** → section **TryHackMe** → déplie
   « **CAPTCHA bloque la connexion ? Importer un cookie de session** » et
   colle la valeur dans le textarea, puis clique **Importer**.

Le backend vérifie que les cookies correspondent bien à un compte connecté
en chargeant `/dashboard`, puis les chiffre en AES-GCM dans la base locale.

> 💡 Tu peux aussi coller l'en-tête `Cookie:` complet (copié depuis l'onglet
> Network) ou un JSON Playwright (`[{name, value, domain, ...}]`). Le backend
> détecte le format automatiquement.

Quand le cookie expirera, l'UI t'indiquera « session expirée » — refais le
même import.

### 5.2 Solution alternative : mode headful (debug)

Si tu préfères automatiser le login **et** résoudre le CAPTCHA toi-même à
chaque connexion, lance le backend hors Docker avec :

```powershell
docker compose stop backend
cd backend
. .\.venv\Scripts\Activate.ps1
$env:THM_HEADFUL = "1"
$env:THM_SLOW_MO_MS = "150"
uvicorn app.main:app --reload --port 8001
```

Au prochain login, Chromium s'ouvre visuellement avec ton email + mot de
passe pré-remplis. Coche le CAPTCHA et clique « Log in » : dès que la page
quitte `/login`, Playwright reprend la main, capture les cookies, et la
fenêtre se ferme.

Inconvénients : pas de display dans le container Docker (donc backend hors
Docker uniquement), et l'opération est manuelle à chaque expiration de
session.

### 5.3 Diagnostics

Si quelque chose se passe mal côté Playwright, trois endpoints t'aident :

- `GET /api/thm/debug/last-login` → JSON avec l'URL atteinte, le nombre de
  champs OTP détectés, les paths des fichiers.
- `GET /api/thm/debug/screenshot` → PNG du dernier état observé.
- `GET /api/thm/debug/html` → dump HTML correspondant.

Les fichiers sont aussi écrits dans `data/thm-debug/` :

```text
data/thm-debug/
├── 01-login-page.png        # avant submit
├── 02-after-submit.png      # après submit
├── 02-captcha.png           # quand CAPTCHA détecté
└── ERR-*.png                # snapshots d'erreur
```
