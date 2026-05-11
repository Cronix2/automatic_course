# Sécurité

## Modèle de menaces

L'application est **mono-utilisateur, auto-hébergée**. Le modèle de menaces couvre :

| Menace | Contrôle |
| --- | --- |
| Vol du fichier `data/app.db` | Tous les secrets sont chiffrés AES-256-GCM. La DB seule est inexploitable. |
| Vol du `.env` (clé maître) **et** de la DB | ⚠️ compromission totale des secrets. Sauvegarde séparément. |
| Injection (SQLi, XSS) | SQLAlchemy paramétré, React échappe par défaut, CSP via headers. |
| CSRF | Cookies `SameSite=Lax`, requêtes mutantes via `fetch` avec `credentials: include` depuis la même origine. |
| Vol de credentials providers | Stockés chiffrés ; clé maître hors-DB. |
| Vol de session TryHackMe | Cookie chiffré, re-login automatique si invalide. |
| Bruteforce login | `slowapi` rate-limit 120 req/min global, à durcir par route en prod. |
| MITM | HSTS en prod, HTTPS recommandé via reverse-proxy (Caddy/Traefik). |
| Prompt injection (LLM) | Le `system prompt` est constant, l'input cours est traité comme données utilisateur. **Ne jamais exécuter** ce qui sort du LLM sans revue. |

## Cryptographie

- **AES-256-GCM** (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).
- **Nonce 96 bits aléatoire** par chiffrement, jamais réutilisé.
- **Associated data = la clé du secret** : un attaquant qui swap `provider.1.api_key` avec `provider.2.api_key` en DB obtient une erreur d'auth GCM.
- **Clé maître 256 bits** générée par `os.urandom(32)` au déploiement.

## Stockage des secrets

✅ En DB chiffré : email/mdp THM, cookie session THM, API keys providers, tokens OAuth.  
❌ **Jamais en clair** ni en logs.  
❌ **Jamais en dur** dans le code (vérifié : aucun token/clé n'apparaît dans le repo).

## Headers HTTP de sécurité

Appliqués par le middleware backend + `nginx.conf` du frontend :

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: microphone=(self), camera=(), geolocation=()`
- `Strict-Transport-Security` en prod uniquement (nécessite HTTPS)

À ajouter en prod derrière un reverse-proxy : `Content-Security-Policy` strict (sources fonts, scripts, connect-src), gestion du HTTPS.

## Bonnes pratiques opérationnelles

1. **Sauvegarde** : `data/app.db` + `.env` doivent être sauvegardés **séparément** (la DB sans la clé maître est inutile, et inversement).
2. **Rotation** de `APP_MASTER_KEY` : non encore automatisée — nécessite un script de re-chiffrement.
3. **Ne jamais exposer** le backend directement sur Internet sans reverse-proxy TLS.
4. **OAuth GitHub** : les secrets `CLIENT_ID`/`CLIENT_SECRET` côté GitHub doivent eux aussi être protégés.

## Audit

Toutes les opérations sensibles (création/suppression de provider, mise à jour credentials THM) peuvent être enregistrées dans la table `audit_log`. À étendre selon vos besoins.
