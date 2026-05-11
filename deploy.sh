#!/usr/bin/env bash
# Déploiement automatique de automatic_course (Linux/macOS).
set -euo pipefail

cd "$(dirname "$0")"

c_cyan="\033[36m"; c_green="\033[32m"; c_yellow="\033[33m"; c_red="\033[31m"; c_magenta="\033[35m"; c_reset="\033[0m"
info()  { echo -e "${c_cyan}[INFO]${c_reset}  $*"; }
ok()    { echo -e "${c_green}[ OK ]${c_reset}  $*"; }
warn()  { echo -e "${c_yellow}[WARN]${c_reset}  $*"; }
fail()  { echo -e "${c_red}[FAIL]${c_reset}  $*"; exit 1; }

# ---- 1. Pre-flight ---------------------------------------------------------
command -v docker >/dev/null 2>&1 || fail "Docker requis."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 requis."
ok "Docker prêt."

if [[ "${1:-}" == "down" ]]; then
    docker compose down
    ok "Containers arrêtés."
    exit 0
fi

# ---- 2. .env ---------------------------------------------------------------
if [[ ! -f .env ]]; then
    [[ -f .env.example ]] || fail ".env.example introuvable."
    cp .env.example .env
    ok ".env créé depuis .env.example."
fi

gen_b64() {
    local n="$1"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 "$n" | tr -d '\n'
    else
        python3 -c "import os,base64,sys;sys.stdout.write(base64.b64encode(os.urandom($n)).decode())"
    fi
}

ensure_secret() {
    local key="$1" bytes="$2" value
    if grep -qE "^${key}=.+$" .env; then
        info "${key} déjà défini."
        return
    fi
    value=$(gen_b64 "$bytes")
    # Escape for sed
    local escaped=${value//\//\\/}
    if grep -qE "^${key}=" .env; then
        sed -i.bak -E "s|^${key}=.*|${key}=${escaped}|" .env && rm -f .env.bak
    else
        echo "${key}=${value}" >> .env
    fi
    ok "Généré ${key}"
}

ensure_secret APP_MASTER_KEY 32
ensure_secret SESSION_SECRET 48

# ---- 3. Build & up ---------------------------------------------------------
if [[ "${1:-}" == "rebuild" ]]; then
    info "Rebuild complet (--no-cache)..."
    docker compose build --no-cache
fi

info "Build & up..."
docker compose up -d --build

FRONT_PORT=$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2)
BACK_PORT=$(grep -E '^BACKEND_PORT=' .env | cut -d= -f2)

ok "automatic_course est lancé."
echo ""
echo -e "  ${c_magenta}Frontend${c_reset} : http://localhost:${FRONT_PORT}"
echo -e "  ${c_magenta}Backend ${c_reset} : http://localhost:${BACK_PORT}/docs"
echo ""
info "Logs : docker compose logs -f"
