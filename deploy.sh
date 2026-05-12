#!/usr/bin/env bash
# ============================================================================
#  Automatic Course — deploy script
#  Linux / macOS / WSL2 + Docker Desktop
#
#  4 phases:
#    1. AUDIT     — détecte l'état actuel (Docker, ports, .env, modèles…)
#    2. REPAIR    — corrige ce qui manque (génération secrets, voix Piper…)
#    3. DEPLOY    — build + up des conteneurs (legacy builder pour éviter
#                   les corruptions WSL2 sur de gros layers)
#    4. VERIFY    — health checks finaux + résumé URLs
#
#  Flags:
#    --rebuild      Force rebuild --no-cache de toutes les images
#    --skip-models  Saute le téléchargement des modèles Piper
#    --yes          Mode non-interactif (accepte tous les défauts)
#    down           Arrête tous les conteneurs et sort
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---- Pretty printing --------------------------------------------------------
if [[ -t 1 ]] && [[ "${NO_COLOR:-}" == "" ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YLW=$'\033[33m'
    C_BLU=$'\033[34m'; C_MAG=$'\033[35m'; C_CYN=$'\033[36m'
else
    C_RESET=""; C_BOLD=""; C_DIM=""
    C_RED=""; C_GRN=""; C_YLW=""; C_BLU=""; C_MAG=""; C_CYN=""
fi

S_OK="${C_GRN}✓${C_RESET}"
S_KO="${C_RED}✗${C_RESET}"
S_WN="${C_YLW}!${C_RESET}"
S_IN="${C_CYN}·${C_RESET}"

banner() {
    local title="$1"
    printf "\n${C_MAG}${C_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}\n"
    printf "${C_MAG}${C_BOLD}  %s${C_RESET}\n" "$title"
    printf "${C_MAG}${C_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}\n\n"
}
step()    { printf "${C_CYN}▸${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$*"; }
ok()      { printf "  %b %s\n" "$S_OK" "$*"; }
warn()    { printf "  %b ${C_YLW}%s${C_RESET}\n" "$S_WN" "$*"; }
ko()      { printf "  %b ${C_RED}%s${C_RESET}\n" "$S_KO" "$*"; }
info()    { printf "  %b %s\n" "$S_IN" "$*"; }
fatal()   { ko "$*"; printf "\n${C_RED}${C_BOLD}Aborted.${C_RESET}\n"; exit 1; }

# ---- Helpers ----------------------------------------------------------------
INTERACTIVE=1
SKIP_MODELS=0
REBUILD=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y)      INTERACTIVE=0 ;;
        --skip-models) SKIP_MODELS=1 ;;
        --rebuild)     REBUILD=1 ;;
        down)
            docker compose down
            ok "Conteneurs arrêtés."
            exit 0
            ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# //; s/^#//'
            exit 0
            ;;
    esac
done

ask() {
    local q="$1" default="${2:-Y}" reply
    if [[ $INTERACTIVE -eq 0 ]]; then
        [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
    fi
    local hint="[Y/n]"; [[ "$default" =~ ^[Nn] ]] && hint="[y/N]"
    read -r -p "  ${C_BOLD}?${C_RESET} $q $hint " reply
    reply=${reply:-$default}
    [[ "$reply" =~ ^[YyOo] ]]
}

port_in_use() {
    local p="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":${p}\$"
    elif command -v lsof >/dev/null 2>&1; then
        lsof -iTCP -sTCP:LISTEN -P 2>/dev/null | awk '{print $9}' | grep -qE ":${p}\$"
    else
        return 1
    fi
}

env_get() {
    local key="$1" default="$2"
    if [[ -f .env ]]; then
        local v
        v=$(grep -E "^${key}=" .env 2>/dev/null | head -1 | cut -d= -f2-)
        [[ -n "$v" ]] && { echo "$v"; return; }
    fi
    echo "$default"
}

gen_b64() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 "$1" | tr -d '\n'
    else
        python3 -c "import os,base64,sys;sys.stdout.write(base64.b64encode(os.urandom($1)).decode())"
    fi
}

# ============================================================================
#  PHASE 1: AUDIT
# ============================================================================
banner "Phase 1 / 4 — Audit du système"

AUDIT_FAILED=0
NEED_REPAIR=()

step "Outils requis"
if command -v docker >/dev/null 2>&1; then
    ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"
else
    ko "docker introuvable"; AUDIT_FAILED=1
fi
if docker compose version >/dev/null 2>&1; then
    ok "docker compose $(docker compose version --short 2>/dev/null || echo v2)"
else
    ko "docker compose v2 introuvable"; AUDIT_FAILED=1
fi
if docker info >/dev/null 2>&1; then
    ok "daemon Docker accessible"
else
    ko "daemon Docker injoignable (Docker Desktop lancé ?)"; AUDIT_FAILED=1
fi

step "Fichier .env"
if [[ -f .env ]]; then
    ok ".env présent"
    for key in APP_MASTER_KEY SESSION_SECRET; do
        if grep -qE "^${key}=.+$" .env; then
            ok "${key} défini"
        else
            warn "${key} manquant"
            NEED_REPAIR+=("env:$key")
        fi
    done
else
    warn ".env absent"
    NEED_REPAIR+=("env:missing")
fi

step "Ports"
FRONT_PORT=$(env_get FRONTEND_PORT 5173)
BACK_PORT=$(env_get BACKEND_PORT 8001)
for entry in "$FRONT_PORT:frontend" "$BACK_PORT:backend"; do
    p="${entry%%:*}"; name="${entry##*:}"
    if port_in_use "$p"; then
        if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -qE "ac-${name}.*:${p}->"; then
            ok "port ${p} occupé par ac-${name} (OK)"
        else
            warn "port ${p} occupé par un autre processus — risque de conflit pour ${name}"
        fi
    else
        ok "port ${p} libre (${name})"
    fi
done

step "Voix Piper (TTS)"
PIPER_VOICE=$(env_get PIPER_VOICE fr_FR-siwis-medium)
if [[ -f "models/piper/${PIPER_VOICE}.onnx" && -f "models/piper/${PIPER_VOICE}.onnx.json" ]]; then
    ok "voix ${PIPER_VOICE} installée"
else
    warn "voix ${PIPER_VOICE} absente — TTS échouera"
    NEED_REPAIR+=("piper:$PIPER_VOICE")
fi

step "WSLg / affichage"
if [[ -n "${DISPLAY:-}" ]] || [[ -e /tmp/.X11-unix/X0 ]]; then
    ok "DISPLAY=${DISPLAY:-:0} (browser-login THM possible)"
else
    warn "pas d'affichage X — le login navigateur THM ne s'affichera pas"
fi

[[ $AUDIT_FAILED -eq 1 ]] && fatal "Pré-requis manquants. Installe-les et relance."

# ============================================================================
#  PHASE 2: REPAIR
# ============================================================================
banner "Phase 2 / 4 — Corrections"

if [[ ${#NEED_REPAIR[@]} -eq 0 ]]; then
    ok "Rien à corriger."
else
    for item in "${NEED_REPAIR[@]}"; do
        case "$item" in
            env:missing)
                step "Création de .env depuis .env.example"
                [[ -f .env.example ]] || fatal ".env.example introuvable"
                cp .env.example .env
                ok ".env créé"
                ;;
            env:APP_MASTER_KEY)
                step "Génération APP_MASTER_KEY"
                v=$(gen_b64 32)
                if grep -qE "^APP_MASTER_KEY=" .env; then
                    sed -i.bak -E "s|^APP_MASTER_KEY=.*|APP_MASTER_KEY=${v//\//\\/}|" .env && rm -f .env.bak
                else
                    echo "APP_MASTER_KEY=${v}" >> .env
                fi
                ok "généré (32 bytes base64)"
                ;;
            env:SESSION_SECRET)
                step "Génération SESSION_SECRET"
                v=$(gen_b64 48)
                if grep -qE "^SESSION_SECRET=" .env; then
                    sed -i.bak -E "s|^SESSION_SECRET=.*|SESSION_SECRET=${v//\//\\/}|" .env && rm -f .env.bak
                else
                    echo "SESSION_SECRET=${v}" >> .env
                fi
                ok "généré (48 bytes base64)"
                ;;
            piper:*)
                voice="${item#piper:}"
                step "Téléchargement de la voix Piper « $voice »"
                if [[ $SKIP_MODELS -eq 1 ]]; then
                    warn "ignoré (--skip-models)"
                elif ask "Télécharger maintenant (~60 Mo) ?" Y; then
                    if [[ -x scripts/download_piper_voice.sh ]]; then
                        scripts/download_piper_voice.sh "$voice" || warn "Echec téléchargement, TTS ne fonctionnera pas"
                    else
                        chmod +x scripts/download_piper_voice.sh 2>/dev/null || true
                        bash scripts/download_piper_voice.sh "$voice" || warn "Echec téléchargement"
                    fi
                else
                    warn "voix non téléchargée — bouton « Lire à voix haute » échouera"
                fi
                ;;
        esac
    done
fi

for key in APP_MASTER_KEY SESSION_SECRET; do
    grep -qE "^${key}=.+$" .env || fatal "${key} toujours vide dans .env"
done

# ============================================================================
#  PHASE 3: DEPLOY
# ============================================================================
banner "Phase 3 / 4 — Déploiement"

# WSL2 + Docker Desktop avec buildkit moderne peut corrompre les gros layers
# (Playwright Chromium ~280 Mo) → forcer le legacy builder par défaut.
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"
info "DOCKER_BUILDKIT=${DOCKER_BUILDKIT} (0 = legacy builder, plus fiable sur WSL2)"

if [[ $REBUILD -eq 1 ]]; then
    step "Rebuild --no-cache --pull"
    docker compose build --no-cache --pull
else
    step "Build (cache autorisé)"
    docker compose build
fi

step "Up (detached)"
docker compose up -d

# ============================================================================
#  PHASE 4: VERIFY
# ============================================================================
banner "Phase 4 / 4 — Vérification"

step "État des conteneurs"
sleep 2
docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' | sed 's/^/  /'

step "Health check backend"
HEALTH_URL="http://localhost:${BACK_PORT}/api/health"
HEALTHY=0
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
        ok "backend répond sur ${HEALTH_URL}"
        HEALTHY=1
        break
    fi
    printf "  ${C_DIM}…attente backend (%d/10)${C_RESET}\r" "$i"
    sleep 2
done
[[ $HEALTHY -eq 0 ]] && {
    ko "backend ne répond pas après 20 s"
    printf "\n${C_YLW}Logs récents :${C_RESET}\n"
    docker compose logs backend --tail=20
    exit 1
}

step "Health check frontend"
if curl -fsS "http://localhost:${FRONT_PORT}" -o /dev/null; then
    ok "frontend servi sur le port ${FRONT_PORT}"
else
    warn "frontend pas encore prêt (peut tarder ~10 s au 1er boot)"
fi

# ---- Final summary ----------------------------------------------------------
printf "\n${C_GRN}${C_BOLD}╔═══════════════════════════════════════════════════════════════════════╗${C_RESET}\n"
printf "${C_GRN}${C_BOLD}║                   ✓  Automatic Course est prêt                        ║${C_RESET}\n"
printf "${C_GRN}${C_BOLD}╚═══════════════════════════════════════════════════════════════════════╝${C_RESET}\n\n"
printf "  ${C_BOLD}Frontend${C_RESET}    ${C_CYN}http://localhost:${FRONT_PORT}${C_RESET}\n"
printf "  ${C_BOLD}Backend ${C_RESET}    ${C_CYN}http://localhost:${BACK_PORT}/docs${C_RESET}  (OpenAPI)\n"
printf "  ${C_BOLD}Logs    ${C_RESET}    ${C_DIM}docker compose logs -f backend${C_RESET}\n"
printf "  ${C_BOLD}Arrêt   ${C_RESET}    ${C_DIM}./deploy.sh down${C_RESET}\n\n"
printf "  ${C_DIM}Premier lancement ? Va dans Réglages pour configurer TryHackMe${C_RESET}\n"
printf "  ${C_DIM}et au moins un provider IA avant d'essayer un cours.${C_RESET}\n\n"
