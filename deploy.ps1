<#
.SYNOPSIS
    Déploiement automatique de automatic_course sous Windows (Docker Compose).
.DESCRIPTION
    - Vérifie Docker
    - Crée .env si absent (à partir de .env.example)
    - Génère APP_MASTER_KEY et SESSION_SECRET cryptographiquement
    - Build + up les containers
#>
param(
    [switch]$Rebuild,
    [switch]$NoCache,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Info($msg)  { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[ OK ]  $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[FAIL]  $msg" -ForegroundColor Red; exit 1 }

# ---- 1. Pre-flight checks --------------------------------------------------
Info "Vérification de Docker..."
try { docker --version | Out-Null } catch { Fail "Docker n'est pas installé ou pas dans le PATH." }
try { docker compose version | Out-Null } catch { Fail "Docker Compose v2 requis (`docker compose`)." }
Ok "Docker prêt."

if ($Down) {
    Info "Arrêt des containers..."
    docker compose down
    Ok "Containers arrêtés."
    exit 0
}

# ---- 2. .env ---------------------------------------------------------------
$envFile = Join-Path $PSScriptRoot ".env"
$envExample = Join-Path $PSScriptRoot ".env.example"

if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) { Fail ".env.example introuvable." }
    Info "Création du .env depuis .env.example..."
    Copy-Item $envExample $envFile
    Ok ".env créé."
}

function Get-RandomB64([int]$bytes) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return [Convert]::ToBase64String($b)
}

function Ensure-EnvSecret([string]$key, [int]$bytes) {
    $content = Get-Content $envFile -Raw
    $pattern = "(?m)^$key=(.*)$"
    $match = [regex]::Match($content, $pattern)
    if (-not $match.Success -or [string]::IsNullOrWhiteSpace($match.Groups[1].Value)) {
        $value = Get-RandomB64 $bytes
        if ($match.Success) {
            $content = [regex]::Replace($content, $pattern, "$key=$value")
        } else {
            $content += "`n$key=$value`n"
        }
        Set-Content -Path $envFile -Value $content -NoNewline
        Ok "Généré $key"
    } else {
        Info "$key déjà défini."
    }
}

Ensure-EnvSecret "APP_MASTER_KEY" 32
Ensure-EnvSecret "SESSION_SECRET" 48

# ---- 3. Build & up ---------------------------------------------------------
$composeArgs = @("compose", "up", "-d", "--build")
if ($NoCache) { $composeArgs = @("compose", "build", "--no-cache") }

if ($Rebuild) {
    Info "Rebuild complet..."
    docker compose build --no-cache
}

Info "Lancement des containers..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail "Échec du docker compose up." }

Ok "automatic_course est lancé."
Write-Host ""
Write-Host "  Frontend  : http://localhost:$((Get-Content .env | Select-String '^FRONTEND_PORT=' | ForEach-Object { $_.Line.Split('=')[1] }))" -ForegroundColor Magenta
Write-Host "  Backend   : http://localhost:$((Get-Content .env | Select-String '^BACKEND_PORT=' | ForEach-Object { $_.Line.Split('=')[1] }))/docs" -ForegroundColor Magenta
Write-Host ""
Info "Logs : docker compose logs -f"
