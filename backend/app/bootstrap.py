"""Bootstrap: ensure critical secrets exist before Settings is loaded.

When the container is started directly (without running deploy.sh first),
APP_MASTER_KEY and SESSION_SECRET may be empty in `.env`. To avoid a hard
crash, we generate them on first boot, persist them to
`data/.bootstrap.env`, and inject them into the process environment so
pydantic-settings picks them up.

The generated values are persisted so that secrets encrypted with the
master key remain decryptable across container restarts. Re-running
deploy.sh later will NOT overwrite them (deploy.sh only fills empty keys).

NOTE: For production deployments the operator SHOULD set these explicitly
in `.env` and back them up. This bootstrap is a safety net, not a
substitute for proper secret management.
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

_BOOTSTRAP_FILENAME = ".bootstrap.env"


def _gen_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


def _gen_session_secret() -> str:
    return secrets.token_urlsafe(48)


def _data_dir() -> Path:
    # Same default as Settings.database_url's `./data/app.db`. We resolve
    # relative to CWD because the FastAPI app runs from /app inside Docker
    # and from the repo root locally.
    p = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_bootstrap(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _write_bootstrap(path: Path, data: dict[str, str]) -> None:
    body = "# Auto-generated secrets. Do NOT commit. Do NOT regenerate.\n"
    body += "# Backing up this file is mandatory: losing it = losing all stored credentials.\n"
    for k, v in data.items():
        body += f"{k}={v}\n"
    path.write_text(body, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best-effort on Windows / restricted FS.
        pass


def ensure_secrets() -> None:
    """Generate APP_MASTER_KEY and SESSION_SECRET if missing.

    Order of resolution per key:
      1. If env var is already set and non-empty, keep it.
      2. Else if `data/.bootstrap.env` has it, load it into env.
      3. Else generate, persist to `data/.bootstrap.env`, set env.
    """
    path = _data_dir() / _BOOTSTRAP_FILENAME
    stored = _read_bootstrap(path)
    dirty = False

    for key, generator in (
        ("APP_MASTER_KEY", _gen_master_key),
        ("SESSION_SECRET", _gen_session_secret),
    ):
        if os.environ.get(key):
            continue
        if stored.get(key):
            os.environ[key] = stored[key]
            continue
        value = generator()
        stored[key] = value
        os.environ[key] = value
        dirty = True
        # Stderr so it appears in `docker logs` without polluting stdout.
        print(
            f"[bootstrap] generated {key} (persisted to {path}). "
            "Back up this file to keep your encrypted secrets recoverable.",
            flush=True,
        )

    if dirty:
        _write_bootstrap(path, stored)
