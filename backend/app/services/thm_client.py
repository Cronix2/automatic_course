"""TryHackMe automation client (Playwright headless).

Handles password login, optional 2FA (TOTP) prompt, session persistence,
and room HTML extraction. All selectors are isolated at the top of the
module to make them easy to update if TryHackMe changes its UI.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
    async_playwright,
)

from app.config import get_settings
from app.schemas.course import CourseContent

# --- Selectors / endpoints (centralize all THM specifics) -------------------
_LOGIN_URL = "/login"
_EMAIL_SEL = (
    "input[name='username'], input[name='email'], "
    "input[type='email'], input[placeholder*='example' i], "
    "input[placeholder*='email' i], input[autocomplete='username']"
)
_PASSWORD_SEL = (
    "input[name='password'], input[type='password'], "
    "input[autocomplete='current-password']"
)
# Be permissive: many sites use <button>Log in</button> without explicit type.
_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "form button:has-text('Log in')",
    "form button:has-text('Sign in')",
    "form button:has-text('Login')",
    "button:has-text('Log in'):not(:has-text('Google')):not(:has-text('LinkedIn')):not(:has-text('GitHub'))",
    "input[type='submit']",
]
_COOKIE_BANNER_SELECTORS = [
    "button:has-text('Allow All')",
    "button:has-text('Accept All')",
    "button:has-text('Tout accepter')",
    "#onetrust-accept-btn-handler",
]
_LOGGED_IN_HINT = "a[href*='/profile'], a[href*='/dashboard']"
# Anything that looks like a 6/7/8-digit TOTP / OTP input.
_TOTP_SEL = (
    "input[name='token'], input[name='code'], input[name='otp'], "
    "input[name='totp'], input[name='mfa'], input[name='twoFactor'], "
    "input[name='two_factor'], input[name='twoFactorCode'], "
    "input[autocomplete='one-time-code'], "
    "input[inputmode='numeric'][maxlength='6'], "
    "input[inputmode='numeric'][maxlength='7'], "
    "input[inputmode='numeric'][maxlength='8'], "
    "input[type='tel'][maxlength='6'], "
    "input[type='text'][maxlength='6'][name*='code' i], "
    "input[type='text'][maxlength='6'][placeholder*='code' i]"
)
_TWOFA_HINTS = (
    "two-factor",
    "two factor",
    "2fa",
    "verification code",
    "authenticator",
    "authentification à deux facteurs",
    "code de vérification",
    "google authenticator",
    "totp",
    "one-time",
    "one time password",
)
_TWOFA_URL_HINTS = ("2fa", "two-factor", "two_factor", "twofactor", "totp", "mfa", "verify")

# reCAPTCHA / hCaptcha widgets that we cannot solve automatically.
_CAPTCHA_SELECTORS = (
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[title*='recaptcha' i]",
    "iframe[title*='hcaptcha' i]",
    ".g-recaptcha",
    "[data-sitekey]",
)

_ROOM_URL_RE = re.compile(
    r"tryhackme\.com/(?:room|r)/([A-Za-z0-9_-]+)", re.IGNORECASE
)


def normalize_room_ref(value: str) -> str:
    """Accept either a raw room code or a full TryHackMe URL.

    Returns the lowercase room code. Raises ValueError if nothing usable.
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("Empty room reference.")
    m = _ROOM_URL_RE.search(v)
    if m:
        return m.group(1).lower()
    if re.fullmatch(r"[A-Za-z0-9_-]+", v):
        return v.lower()
    raise ValueError(f"Could not parse room code from: {value!r}")


@dataclass
class THMSession:
    cookies: list[dict]

    def to_json(self) -> str:
        return json.dumps(self.cookies)

    @classmethod
    def from_json(cls, raw: str) -> "THMSession":
        return cls(cookies=json.loads(raw))


class THMTwoFactorRequired(Exception):
    """Raised when the login flow lands on a 2FA prompt."""

    def __init__(self, challenge_id: str) -> None:
        super().__init__("Two-factor authentication required.")
        self.challenge_id = challenge_id


class THMCaptchaBlocked(Exception):
    """Raised when TryHackMe shows a CAPTCHA that we cannot solve automatically.

    The user must either import a session cookie manually or run the backend
    with ``THM_HEADFUL=1`` so they can solve the CAPTCHA in the Playwright
    window themselves.
    """

    def __init__(self, message: str = "TryHackMe demande un CAPTCHA — connexion automatique impossible.") -> None:
        super().__init__(message)


@dataclass
class _PendingLogin:
    """In-progress login waiting for a 2FA code."""

    pw: object
    browser: Browser
    context: BrowserContext
    page: Page
    created_at: float = field(default_factory=time.time)


class _PendingLoginStore:
    """In-memory store of half-completed logins (TTL + bounded size)."""

    _TTL_S = 300
    _MAX = 8

    def __init__(self) -> None:
        self._items: Dict[str, _PendingLogin] = {}
        self._lock = asyncio.Lock()

    async def put(self, pending: _PendingLogin) -> str:
        async with self._lock:
            await self._gc_locked()
            if len(self._items) >= self._MAX:
                oldest = min(self._items.items(), key=lambda kv: kv[1].created_at)
                await self._close(oldest[1])
                self._items.pop(oldest[0], None)
            cid = secrets.token_urlsafe(16)
            self._items[cid] = pending
            return cid

    async def pop(self, cid: str) -> Optional[_PendingLogin]:
        async with self._lock:
            await self._gc_locked()
            return self._items.pop(cid, None)

    async def _gc_locked(self) -> None:
        now = time.time()
        stale = [k for k, v in self._items.items() if now - v.created_at > self._TTL_S]
        for k in stale:
            await self._close(self._items[k])
            self._items.pop(k, None)

    @staticmethod
    async def _close(p: _PendingLogin) -> None:
        for closer in (p.context.close, p.browser.close, getattr(p.pw, "stop", None)):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:
                pass


_PENDING = _PendingLoginStore()


async def _dismiss_cookies(page: Page) -> None:
    """Best-effort: click any visible cookie-consent button so it doesn't
    intercept later clicks. Never raises."""
    for sel in _COOKIE_BANNER_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=1500)
                logger.info("THM: dismissed cookie banner ({})", sel)
                return
        except Exception:
            continue


async def _click_first(page: Page, selectors: List[str], *, what: str) -> bool:
    """Try each selector until one is visible & clickable. Returns True on
    success. Logs each attempt."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            count = await loc.count()
            if count == 0:
                logger.debug("THM click '{}': selector miss [{}]", what, sel)
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            await loc.click(timeout=3000)
            logger.info("THM click '{}': matched [{}]", what, sel)
            return True
        except Exception as e:
            logger.debug("THM click '{}' failed on [{}]: {}", what, sel, e)
            continue
    return False


# ---- Debug snapshot helpers ------------------------------------------------
_LAST_SNAPSHOT: Dict[str, Any] = {
    "name": None,
    "url": None,
    "title": None,
    "screenshot": None,
    "html": None,
    "detected_2fa": None,
    "matched_otp_selectors": 0,
    "ts": None,
}


def get_last_snapshot() -> Dict[str, Any]:
    return dict(_LAST_SNAPSHOT)


async def _snapshot(page: Page, name: str, detected_2fa: Optional[bool] = None) -> None:
    """Persist a screenshot + HTML dump to the configured debug dir.

    Always best-effort: never raises. Useful to diagnose why 2FA detection
    might be failing — drop into ``data/thm-debug/`` and inspect.
    """
    try:
        settings = get_settings()
        out_dir = Path(settings.thm_debug_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        png_path = out_dir / f"{name}.png"
        html_path = out_dir / f"{name}.html"
        try:
            await page.screenshot(path=str(png_path), full_page=True)
        except Exception as e:
            logger.warning("THM snapshot screenshot failed: {}", e)
            png_path = None  # type: ignore[assignment]
        try:
            html = await page.content()
            html_path.write_text(html, encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("THM snapshot html failed: {}", e)
            html_path = None  # type: ignore[assignment]
        try:
            url = page.url
        except Exception:
            url = None
        try:
            title = await page.title()
        except Exception:
            title = None
        otp_count = 0
        try:
            otp_count = await page.locator(_TOTP_SEL).count()
        except Exception:
            pass
        _LAST_SNAPSHOT.update(
            {
                "name": name,
                "url": url,
                "title": title,
                "screenshot": str(png_path) if png_path else None,
                "html": str(html_path) if html_path else None,
                "detected_2fa": detected_2fa,
                "matched_otp_selectors": otp_count,
                "ts": time.time(),
            }
        )
        logger.info(
            "THM snapshot '{}' saved (url={}, otp_inputs={}, detected_2fa={})",
            name, url, otp_count, detected_2fa,
        )
    except Exception as e:
        logger.warning("THM snapshot '{}' failed entirely: {}", name, e)


async def _detect_captcha(page: Page) -> bool:
    """Detect a reCAPTCHA / hCaptcha widget on the page."""
    for sel in _CAPTCHA_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                try:
                    if await loc.is_visible():
                        return True
                except Exception:
                    # The widget might be inside an iframe and not directly
                    # "visible" in Playwright's sense; presence is enough.
                    return True
        except Exception:
            continue
    return False


async def _detect_2fa(page: Page) -> bool:
    # URL hint first — cheapest and most reliable signal.
    try:
        url = (page.url or "").lower()
        if any(h in url for h in _TWOFA_URL_HINTS):
            logger.info("THM 2FA detected via URL: {}", url)
            return True
    except Exception:
        pass
    # Visible OTP-shaped input.
    try:
        loc = page.locator(_TOTP_SEL)
        count = await loc.count()
        if count > 0:
            for i in range(min(count, 5)):
                try:
                    if await loc.nth(i).is_visible():
                        logger.info("THM 2FA detected via OTP selector (#{} visible)", i)
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    # Body-text heuristic last (noisier but catches custom layouts).
    try:
        body = (await page.content()).lower()
    except Exception:
        return False
    for h in _TWOFA_HINTS:
        if h in body:
            # Ignore false positives where the word appears only in <head>/scripts
            # by also requiring an OTP-ish input or a heading containing it.
            try:
                if (await page.locator(_TOTP_SEL).count()) > 0:
                    logger.info("THM 2FA detected via body hint '{}' + OTP input", h)
                    return True
            except Exception:
                pass
            # Headline-style hint (h1/h2/h3 containing the keyword).
            try:
                hloc = page.locator(
                    f"h1:has-text('{h}'), h2:has-text('{h}'), h3:has-text('{h}'), legend:has-text('{h}')"
                )
                if await hloc.count() > 0:
                    logger.info("THM 2FA detected via heading hint '{}'", h)
                    return True
            except Exception:
                pass
    return False


class THMClient:
    """Async TryHackMe automation.

    Use as:
        async with THMClient() as thm:
            session = await thm.login(email, password)
            # may raise THMTwoFactorRequired -> call submit_2fa(challenge_id, code)
            content = await thm.fetch_room(session, "introtosecurity")
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pw = None
        self._browser: Browser | None = None

    # Stealth script: hide Playwright/automation fingerprints to reduce
    # the chance of TryHackMe showing a CAPTCHA.  Covers the most common
    # signals reCAPTCHA / Cloudflare Turnstile inspect.
    _STEALTH_SCRIPT = """
        // 1. navigator.webdriver -> undefined (the #1 automation tell)
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // 2. Realistic plugins / mimeTypes (empty array is a tell)
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const pdf = {name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'};
                return [pdf, pdf, pdf, pdf, pdf];
            }
        });
        Object.defineProperty(navigator, 'mimeTypes', {get: () => [{type: 'application/pdf'}]});

        // 3. Languages (must match Accept-Language header sent by Chromium)
        Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR','fr','en-US','en']});

        // 4. window.chrome object (missing in headless)
        if (!window.chrome) {
            window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
        }

        // 5. Permissions API consistency
        const _origQuery = window.navigator.permissions && window.navigator.permissions.query;
        if (_origQuery) {
            window.navigator.permissions.query = (p) =>
                p.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : _origQuery(p);
        }

        // 6. WebGL vendor / renderer (headless reports SwiftShader)
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
            if (p === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
            return getParameter.call(this, p);
        };

        // 7. Hardware concurrency / device memory (default 1 is a tell)
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

        // 8. Hide that 'webdriver' is a property on window/document
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    """
    # Chrome 150 stable (May 2026).  Older UAs are now flagged by Google.
    _STEALTH_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    )
    _LAUNCH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=IsolateOrigins,site-per-process",
    ]

    async def __aenter__(self) -> "THMClient":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=not self._settings.thm_headful,
            slow_mo=self._settings.thm_slow_mo_ms or 0,
            args=self._LAUNCH_ARGS,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def _new_context(self, session: Optional[THMSession] = None) -> BrowserContext:
        assert self._browser is not None
        ctx = await self._browser.new_context(user_agent=self._STEALTH_UA)
        await ctx.add_init_script(self._STEALTH_SCRIPT)
        if session:
            await ctx.add_cookies(session.cookies)
        return ctx

    # ------------------------------------------------------------------
    async def login(self, email: str, password: str) -> THMSession:
        """Submit username/password.

        Returns a `THMSession` on success, or raises `THMTwoFactorRequired`.
        Uses a dedicated Playwright instance so the context can outlive the
        method call if 2FA is required.
        """
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=not self._settings.thm_headful,
            slow_mo=self._settings.thm_slow_mo_ms or 0,
            args=self._LAUNCH_ARGS,
        )
        ctx = await browser.new_context(user_agent=self._STEALTH_UA)
        await ctx.add_init_script(self._STEALTH_SCRIPT)
        owns_resources = True
        try:
            page: Page = await ctx.new_page()
            await page.goto(
                self._settings.thm_base_url + _LOGIN_URL, wait_until="domcontentloaded"
            )
            try:
                await page.wait_for_selector(_EMAIL_SEL, timeout=10000)
            except Exception:
                logger.warning("THM login: email selector not visible yet.")
            await _dismiss_cookies(page)
            await _snapshot(page, "01-login-page")

            # ------------------------------------------------------------------
            # CAPTCHA handling. If we detect a CAPTCHA *before* attempting the
            # password submit:
            #   - headful: pre-fill credentials and wait for the user to solve
            #     the CAPTCHA and click "Log in" themselves.
            #   - headless: bail out with a clear error so the UI can tell the
            #     user to either switch to headful mode or import cookies.
            # ------------------------------------------------------------------
            try:
                await page.fill(_EMAIL_SEL, email)
            except Exception as e:
                await _snapshot(page, "ERR-fill-email")
                raise RuntimeError(f"Could not fill email field: {e}")
            try:
                await page.fill(_PASSWORD_SEL, password)
            except Exception as e:
                await _snapshot(page, "ERR-fill-password")
                raise RuntimeError(f"Could not fill password field: {e}")

            if await _detect_captcha(page):
                logger.warning("THM login: CAPTCHA widget detected on /login.")
                await _snapshot(page, "02-captcha")
                if not self._settings.thm_headful:
                    raise THMCaptchaBlocked()
                logger.info(
                    "THM headful: waiting up to 5 min for user to solve CAPTCHA "
                    "and submit the form manually..."
                )
                try:
                    await page.wait_for_url(
                        lambda u: "/login" not in (u or "").lower(),
                        timeout=300_000,
                    )
                except Exception:
                    await _snapshot(page, "ERR-captcha-timeout")
                    raise THMCaptchaBlocked(
                        "Timeout: CAPTCHA non résolu dans le délai imparti."
                    )
            else:
                if not await _click_first(page, _SUBMIT_SELECTORS, what="login-submit"):
                    logger.warning("THM login: no submit button matched; pressing Enter.")
                    try:
                        await page.locator(_PASSWORD_SEL).first.press("Enter")
                    except Exception as e:
                        await _snapshot(page, "ERR-submit")
                        raise RuntimeError(f"Could not submit login form: {e}")
            # Wait either for a URL change away from /login OR for an OTP
            # input to appear OR for the profile link to show up.
            try:
                await page.wait_for_function(
                    """() => {
                        const p = location.pathname.toLowerCase();
                        if (p && p !== '/login' && p !== '/signin') return true;
                        if (document.querySelector("input[autocomplete='one-time-code'], input[name='token'], input[name='otp'], input[name='code'], input[name='totp']")) return true;
                        if (document.querySelector("a[href*='/profile']")) return true;
                        return false;
                    }""",
                    timeout=15000,
                )
            except Exception:
                pass
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            logger.info("THM login: post-submit URL = {}", page.url)

            detected = await _detect_2fa(page)
            await _snapshot(page, "02-after-submit", detected_2fa=detected)

            if detected:
                pending = _PendingLogin(pw=pw, browser=browser, context=ctx, page=page)
                cid = await _PENDING.put(pending)
                owns_resources = False  # ownership transferred
                logger.info("THM login: 2FA required (challenge {})", cid)
                raise THMTwoFactorRequired(cid)

            try:
                await page.wait_for_selector(_LOGGED_IN_HINT, timeout=10000)
            except Exception:
                logger.warning(
                    "THM login: profile link not detected (UI may have changed)."
                )
            cookies = await ctx.cookies()
            if not cookies:
                raise RuntimeError("THM login failed: no cookies returned.")
            return THMSession(cookies=cookies)
        except THMTwoFactorRequired:
            raise
        except THMCaptchaBlocked:
            raise
        except Exception as e:
            # Capture a final snapshot so we can debug whatever blew up.
            try:
                page_ref = ctx.pages[-1] if ctx.pages else None
                if page_ref is not None:
                    await _snapshot(page_ref, "ERR-login")
            except Exception:
                pass
            logger.exception("THM login: unexpected error: {}", e)
            raise
        finally:
            if owns_resources:
                for closer in (ctx.close, browser.close, pw.stop):
                    try:
                        await closer()
                    except Exception:
                        pass

    async def submit_2fa(self, challenge_id: str, code: str) -> THMSession:
        """Complete a login challenge by submitting the OTP code."""
        pending = await _PENDING.pop(challenge_id)
        if pending is None:
            raise RuntimeError(
                "Two-factor challenge expired or unknown. Please log in again."
            )
        ctx = pending.context
        page = pending.page
        try:
            try:
                await page.fill(_TOTP_SEL, code.strip())
            except Exception as e:
                raise RuntimeError(f"Could not enter 2FA code: {e}")
            if not await _click_first(page, _SUBMIT_SELECTORS, what="2fa-submit"):
                # Many TOTP forms auto-submit on the last digit; try Enter.
                try:
                    await page.locator(_TOTP_SEL).first.press("Enter")
                except Exception:
                    pass
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            if await _detect_2fa(page):
                raise RuntimeError("Invalid 2FA code.")
            try:
                await page.wait_for_selector(_LOGGED_IN_HINT, timeout=10000)
            except Exception:
                logger.warning("THM 2FA: profile link not detected; capturing cookies.")
            cookies = await ctx.cookies()
            if not cookies:
                raise RuntimeError("THM 2FA submit failed: no cookies returned.")
            return THMSession(cookies=cookies)
        finally:
            for closer in (ctx.close, pending.browser.close, pending.pw.stop):  # type: ignore[attr-defined]
                try:
                    await closer()
                except Exception:
                    pass

    async def is_session_valid(self, session: THMSession) -> bool:
        """Check session validity via a lightweight httpx request.

        Strategy: GET /dashboard with follow_redirects=False.
        - TryHackMe returns 302 → /login for unauthenticated requests.
        - TryHackMe returns 200 (SPA shell) for authenticated requests.
        """
        import httpx

        cookie_header = "; ".join(
            f"{c['name']}={c['value']}" for c in session.cookies
        )
        logger.debug(
            "THM is_session_valid: checking with {} cookies",
            len(session.cookies),
        )
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=False,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    ),
                    "Cookie": cookie_header,
                },
            ) as client:
                resp = await client.get(
                    self._settings.thm_base_url + "/dashboard"
                )
                location = resp.headers.get("location", "")
                valid = resp.status_code == 200 or (
                    resp.status_code in (301, 302, 307, 308)
                    and "/login" not in location
                )
                logger.info(
                    "THM is_session_valid: /dashboard → {} location={!r} valid={}",
                    resp.status_code,
                    location,
                    valid,
                )
                return valid
        except Exception as exc:
            logger.warning("THM is_session_valid error: {}", exc)
            return False

    # ------------------------------------------------------------------
    async def await_manual_login(
        self,
        on_ready_url: str | None = None,
        timeout_s: int = 300,
    ) -> THMSession:
        """Open a headful browser, let the user log in manually, then capture cookies.

        The browser is *always* launched headful regardless of THM_HEADFUL setting.
        If DISPLAY is not set (Docker without WSLg), a virtual framebuffer (Xvfb)
        is started automatically on :99.
        Waits up to ``timeout_s`` seconds for the user to leave the /login page.
        """
        xvfb_proc: subprocess.Popen | None = None
        if not os.environ.get("DISPLAY"):
            try:
                xvfb_proc = subprocess.Popen(
                    ["Xvfb", ":99", "-screen", "0", "1280x900x24"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                os.environ["DISPLAY"] = ":99"
                await asyncio.sleep(1)  # let Xvfb initialise
                logger.info("Xvfb started on :99 for headful browser-login")
            except FileNotFoundError:
                raise RuntimeError(
                    "Impossible d'ouvrir un navigateur : pas d'affichage (DISPLAY) "
                    "et Xvfb non disponible. Lance le backend localement hors Docker."
                )

        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.launch(
                headless=False,
                slow_mo=80,
                args=self._LAUNCH_ARGS,
            )
            ctx = await browser.new_context(user_agent=self._STEALTH_UA)
            await ctx.add_init_script(self._STEALTH_SCRIPT)
            page = await ctx.new_page()
            await page.goto(
                (on_ready_url or self._settings.thm_base_url) + _LOGIN_URL,
                wait_until="domcontentloaded",
            )
            await _dismiss_cookies(page)
            # Wait until the user navigates away from the login page
            await page.wait_for_url(
                lambda u: "/login" not in u.lower(),
                timeout=timeout_s * 1000,
            )
            cookies = await ctx.cookies()
            if not cookies:
                raise RuntimeError("Aucun cookie récupéré après connexion.")
            return THMSession(cookies=cookies)
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await pw.stop()
            except Exception:
                pass
            if xvfb_proc is not None:
                xvfb_proc.terminate()
                os.environ.pop("DISPLAY", None)

    # ------------------------------------------------------------------
    async def fetch_room(self, session: THMSession, room_code: str) -> CourseContent:
        """Fetch a TryHackMe room, including the content of every task.

        Strategy:
        1. Navigate to /room/<code> and wait for the SPA to hydrate.
        2. Locate the task list (sidebar buttons) via robust selectors.
        3. Click each task in turn, wait for the task content to render,
           and concatenate the resulting markdown.
        Falls back to single-page extraction if no task list is found.
        """
        ctx = await self._new_context(session)
        try:
            # Log session cookies for diagnosis (name/domain only, no value)
            try:
                cookie_summary = [
                    f"{c.get('name')}@{c.get('domain')}" for c in (session.cookies or [])
                ]
                logger.info(
                    "fetch_room: %d cookies attached: %s",
                    len(cookie_summary),
                    cookie_summary,
                )
            except Exception:
                pass

            page = await ctx.new_page()
            url = f"{self._settings.thm_base_url}/room/{room_code}"
            logger.info("fetch_room: navigating to %s", url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except PWTimeout:
                logger.warning("fetch_room: domcontentloaded timeout, continuing anyway")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                logger.info("fetch_room: networkidle not reached (SPA), continuing")

            final_url = page.url
            title = await page.title()
            logger.info("fetch_room: final_url=%s title=%r", final_url, title)

            if "/login" in final_url.lower() or "/signin" in final_url.lower():
                try:
                    await page.screenshot(path=f"/tmp/thm_fetch_fail_{room_code}.png")
                    html_dump = await page.content()
                    with open(f"/tmp/thm_fetch_fail_{room_code}.html", "w") as f:
                        f.write(html_dump)
                except Exception:
                    pass
                raise RuntimeError(
                    "La session TryHackMe a expiré côté serveur (redirection vers /login). "
                    "Reconnecte-toi via 'Ouvrir le navigateur et se connecter'."
                )

            # ---- Per-task scraping ----------------------------------------
            # Step A (JS): locate every task HEADER node in document order
            # and return a stable handle (we attach data-thm-task-idx=N).
            # Step B (Python/Playwright): for each header, click & wait, then
            # capture the DOM range between this header and the next one.
            tag_headers_js = r"""
            () => {
              const taskRe = /^Task\s+\d+\b/i;
              // Strip any prior tagging
              document.querySelectorAll('[data-thm-task-idx]').forEach(el => {
                el.removeAttribute('data-thm-task-idx');
                el.removeAttribute('data-thm-task-title');
              });

              const all = Array.from(document.querySelectorAll(
                'button, [role="button"], [aria-expanded], h1, h2, h3, h4, [class*="task" i]'
              ));
              const seen = new Set();
              const headers = [];
              for (const el of all) {
                const txt = (el.innerText || '').trim();
                if (!txt) continue;
                const first = txt.split('\n')[0].trim();
                if (!taskRe.test(first)) continue;
                if (first.length > 250) continue;
                if (seen.has(first)) continue;
                seen.add(first);
                headers.push({el, title: first});
              }
              // Sort by document order
              headers.sort((a, b) => {
                const pos = a.el.compareDocumentPosition(b.el);
                if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
                if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
                return 0;
              });
              headers.forEach((h, i) => {
                h.el.setAttribute('data-thm-task-idx', String(i));
                h.el.setAttribute('data-thm-task-title', h.title);
              });
              return headers.map((h, i) => ({idx: i, title: h.title}));
            }
            """
            tagged = await page.evaluate(tag_headers_js)
            logger.info("fetch_room: tagged %d task headers: %s",
                        len(tagged), [t["title"] for t in tagged])

            task_payloads: List[dict] = []
            for entry in tagged:
                idx = entry["idx"]
                ttitle = entry["title"]

                # ---- Click phase ------------------------------------------
                # Strategy: try a REAL Playwright click first (real mouse
                # event → React handlers fire reliably). If that times out
                # or fails, fall back to multi-target JS dispatch on
                # ancestors and descendants.
                clicked = False
                header_loc = page.locator(f'[data-thm-task-idx="{idx}"]').first
                try:
                    await header_loc.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                # Capture the text BEFORE click so we can detect a body change.
                before_main_text = ""
                try:
                    before_main_text = await page.evaluate(
                        "() => ((document.querySelector('main') || document.body).innerText || '').trim()"
                    )
                except Exception:
                    before_main_text = ""

                try:
                    await header_loc.click(timeout=2500, force=True)
                    clicked = True
                except Exception as exc:
                    logger.debug(
                        "fetch_room: real click failed for task %d (%s): %s — trying JS dispatch",
                        idx, ttitle, exc,
                    )
                    # Try clicking a descendant button if the header itself
                    # is not the clickable target.
                    try:
                        descendant_btn = page.locator(
                            f'[data-thm-task-idx="{idx}"] button, '
                            f'[data-thm-task-idx="{idx}"] [role="button"], '
                            f'[data-thm-task-idx="{idx}"] [aria-expanded]'
                        ).first
                        await descendant_btn.click(timeout=1500, force=True)
                        clicked = True
                    except Exception:
                        pass

                if not clicked:
                    try:
                        await page.evaluate(
                            """
                            (idx) => {
                              const h = document.querySelector(`[data-thm-task-idx="${idx}"]`);
                              if (!h) return false;
                              h.scrollIntoView({block: 'center'});
                              const fire = (n) => {
                                if (!n) return;
                                try { n.click(); } catch (e) {}
                                try {
                                  n.dispatchEvent(new MouseEvent('click', {
                                    bubbles: true, cancelable: true, view: window
                                  }));
                                } catch (e) {}
                              };
                              let node = h;
                              for (let i = 0; i < 6 && node; i++) {
                                fire(node);
                                node = node.parentElement;
                              }
                              h.querySelectorAll(
                                'button, [role="button"], [aria-expanded]'
                              ).forEach(fire);
                              return true;
                            }
                            """,
                            idx,
                        )
                        clicked = True
                    except Exception as exc:
                        logger.debug(
                            "fetch_room: JS click also failed for task %d (%s): %s",
                            idx, ttitle, exc,
                        )

                # ---- Wait phase -------------------------------------------
                # Tasks display one at a time → after clicking, <main> text
                # must change (new body becomes visible, old one disappears).
                # Poll up to 4s for: (1) main text changed AND (2) range
                # between header[idx] and header[idx+1] is non-empty.
                payload = None
                for _ in range(27):  # 27 * 150ms ≈ 4s
                    payload = await page.evaluate(
                        """
                        (idx) => {
                          const cur = document.querySelector(`[data-thm-task-idx="${idx}"]`);
                          if (!cur) return null;
                          const nxt = document.querySelector(`[data-thm-task-idx="${idx + 1}"]`);
                          try {
                            const range = document.createRange();
                            range.setStartAfter(cur);
                            if (nxt) {
                              range.setEndBefore(nxt);
                            } else {
                              const main = document.querySelector('main') || document.body;
                              if (main.lastChild) range.setEndAfter(main.lastChild);
                              else return null;
                            }
                            const frag = range.cloneContents();
                            const tmp = document.createElement('div');
                            tmp.appendChild(frag);
                            const mainEl = document.querySelector('main') || document.body;
                            return {
                              html: tmp.innerHTML,
                              text_len: (tmp.innerText || '').trim().length,
                              main_text: (mainEl.innerText || '').trim(),
                            };
                          } catch (e) {
                            return {error: String(e)};
                          }
                        }
                        """,
                        idx,
                    )
                    if not payload:
                        await page.wait_for_timeout(150)
                        continue
                    has_body = payload.get("text_len", 0) > 120
                    main_changed = payload.get("main_text", "") != before_main_text
                    if has_body and (main_changed or idx == 0):
                        break
                    await page.wait_for_timeout(150)

                if not payload:
                    payload = {"html": "", "text_len": 0}
                payload.pop("main_text", None)
                payload["title"] = ttitle
                payload["clicked"] = clicked
                task_payloads.append(payload)
                logger.info(
                    "fetch_room: task %d %r → clicked=%s text_len=%d",
                    idx, ttitle, clicked, payload.get("text_len", 0),
                )

            logger.info(
                "fetch_room: per-task extracted %d tasks: %s",
                len(task_payloads),
                [(p.get("title"), p.get("text_len")) for p in task_payloads],
            )

            # ---- Fallback A: sidebar navigation links ---------------------
            # If most tasks have no content, the headers we clicked are
            # probably anchor/heading nodes in the article view, not the
            # sidebar nav items. Try clicking the sidebar list instead and
            # capture page.main after each click.
            empty_count = sum(1 for p in task_payloads if p.get("text_len", 0) < 80)
            if task_payloads and empty_count >= max(2, len(task_payloads) // 2):
                # Dump page state for debugging
                try:
                    await page.screenshot(path=f"/tmp/thm_fetch_dom_{room_code}.png", full_page=True)
                    dom_html = await page.content()
                    with open(f"/tmp/thm_fetch_dom_{room_code}.html", "w") as f:
                        f.write(dom_html)
                    logger.info(
                        "fetch_room: dumped DOM to /tmp/thm_fetch_dom_%s.{png,html}",
                        room_code,
                    )
                except Exception:
                    pass

                logger.info(
                    "fetch_room: %d/%d tasks empty — trying sidebar nav fallback",
                    empty_count,
                    len(task_payloads),
                )
                # Look for sidebar items (left nav) whose text matches /^Task N/
                sidebar_js = r"""
                () => {
                  const taskRe = /^Task\s+\d+\b/i;
                  // Sidebar items are typically <a> or clickable <div> in a
                  // narrow left column. Heuristic: visible elements with
                  // task-like text whose width < 320px.
                  const candidates = Array.from(document.querySelectorAll(
                    'a, [role="button"], [role="link"], button, li'
                  ));
                  const seen = new Set();
                  const items = [];
                  for (const el of candidates) {
                    const txt = (el.innerText || '').trim();
                    if (!txt) continue;
                    const first = txt.split('\n')[0].trim();
                    if (!taskRe.test(first)) continue;
                    if (first.length > 250) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 380) continue;  // not sidebar
                    if (rect.width === 0 || rect.height === 0) continue;
                    if (seen.has(first)) continue;
                    seen.add(first);
                    items.push({el, title: first, x: rect.x});
                  }
                  items.sort((a, b) => {
                    const pos = a.el.compareDocumentPosition(b.el);
                    if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
                    if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
                    return 0;
                  });
                  document.querySelectorAll('[data-thm-nav-idx]').forEach(el => {
                    el.removeAttribute('data-thm-nav-idx');
                  });
                  items.forEach((it, i) => {
                    it.el.setAttribute('data-thm-nav-idx', String(i));
                  });
                  return items.map((it, i) => ({idx: i, title: it.title}));
                }
                """
                nav_items = await page.evaluate(sidebar_js)
                logger.info("fetch_room: sidebar fallback found %d items", len(nav_items))

                if nav_items:
                    new_payloads: List[dict] = []
                    for entry in nav_items:
                        nidx = entry["idx"]
                        ntitle = entry["title"]
                        try:
                            await page.evaluate(
                                """
                                (idx) => {
                                  const el = document.querySelector(`[data-thm-nav-idx="${idx}"]`);
                                  if (!el) return;
                                  el.scrollIntoView({block: 'center'});
                                  try { el.click(); } catch (e) {}
                                  try {
                                    el.dispatchEvent(new MouseEvent('click', {
                                      bubbles: true, cancelable: true, view: window
                                    }));
                                  } catch (e) {}
                                }
                                """,
                                nidx,
                            )
                        except Exception as exc:
                            logger.debug("fetch_room: sidebar click failed for %s: %s", ntitle, exc)
                            continue
                        await page.wait_for_timeout(400)
                        # Capture <main> content
                        body_data = await page.evaluate(
                            """
                            () => {
                              const main = document.querySelector('main') || document.body;
                              return {
                                html: main.innerHTML,
                                text_len: (main.innerText || '').trim().length,
                              };
                            }
                            """
                        )
                        if body_data:
                            body_data["title"] = ntitle
                            new_payloads.append(body_data)
                    # Use sidebar payloads if they yielded more content
                    new_with_content = sum(1 for p in new_payloads if p.get("text_len", 0) > 200)
                    if new_with_content > (len(task_payloads) - empty_count):
                        logger.info(
                            "fetch_room: sidebar fallback succeeded (%d tasks with content)",
                            new_with_content,
                        )
                        task_payloads = new_payloads

            sections_md: List[str] = []
            section_titles: List[str] = []

            if task_payloads:
                for p in task_payloads:
                    title_t = (p.get("title") or "").strip() or "Task"
                    html_frag = p.get("html") or ""
                    if not html_frag or p.get("text_len", 0) < 80:
                        # Empty or just the header — keep title as section
                        # marker but no body.
                        logger.info("fetch_room: task %r has no body", title_t)
                        sections_md.append(f"## {title_t}\n\n_(Aucun contenu visible)_")
                        section_titles.append(title_t)
                        continue
                    body_md = self._extract_markdown_fragment(html_frag)
                    if not body_md:
                        body_md = "_(Contenu non extractible)_"
                    # Remove duplicate title at the top of body
                    if body_md.lstrip().lower().startswith(title_t.lower()):
                        body_md = body_md.split("\n", 1)[1] if "\n" in body_md else ""
                    sections_md.append(f"## {title_t}\n\n{body_md.strip()}")
                    section_titles.append(title_t)

            if not sections_md:
                logger.warning("fetch_room: no per-task content, falling back to whole-page scrape")
                html = await page.content()
                return self._html_to_markdown(html, room_code=room_code, title=title)

            markdown = "\n\n".join(sections_md)
            logger.info(
                "fetch_room: aggregated %d tasks, %d chars total",
                len(sections_md),
                len(markdown),
            )
            return CourseContent(
                room_code=room_code,
                title=title or room_code,
                markdown=markdown,
                sections=section_titles,
            )
        finally:
            await ctx.close()

    @staticmethod
    def _extract_markdown_fragment(html: str) -> str:
        """Extract text/markdown from an HTML fragment (single task body)."""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "button"]):
            tag.decompose()
        parts: List[str] = []
        for el in soup.descendants:
            name = getattr(el, "name", None)
            if name in {"h1", "h2", "h3", "h4"}:
                t = el.get_text(" ", strip=True)
                if t:
                    parts.append(f"\n### {t}\n")
            elif name == "p":
                t = el.get_text(" ", strip=True)
                if t:
                    parts.append(t)
            elif name == "li":
                t = el.get_text(" ", strip=True)
                if t:
                    parts.append(f"- {t}")
            elif name == "pre":
                t = el.get_text("", strip=True)
                if t:
                    parts.append(f"\n```\n{t}\n```\n")
            elif name == "code" and el.parent and el.parent.name != "pre":
                t = el.get_text("", strip=True)
                if t and len(t) < 200:
                    parts.append(f"`{t}`")
        return "\n".join(p for p in parts if p)


    @staticmethod
    def _html_to_markdown(html: str, *, room_code: str, title: str) -> CourseContent:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        main = soup.find("main") or soup.body or soup
        text_parts: List[str] = []
        sections: List[str] = []
        for el in main.descendants:
            name = getattr(el, "name", None)
            if name in {"h1", "h2", "h3"}:
                heading = el.get_text(" ", strip=True)
                if heading:
                    sections.append(heading)
                    text_parts.append(f"\n## {heading}\n")
            elif name == "p":
                t = el.get_text(" ", strip=True)
                if t:
                    text_parts.append(t)
            elif name == "li":
                t = el.get_text(" ", strip=True)
                if t:
                    text_parts.append(f"- {t}")
            elif name == "code":
                t = el.get_text("", strip=True)
                if t and len(t) < 200:
                    text_parts.append(f"`{t}`")
        markdown = "\n".join(p for p in text_parts if p)
        return CourseContent(
            room_code=room_code,
            title=title or room_code,
            markdown=markdown,
            sections=sections,
        )
