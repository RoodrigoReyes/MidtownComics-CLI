"""Automated and interactive browser authentication for Midtown Comics."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import urljoin

from .credentials import CONFIG_DIR, read_credentials, save_session

LOGIN_URL = "https://www.midtowncomics.com/login"
BASE_URL = "https://www.midtowncomics.com"
PROFILE_DIR = CONFIG_DIR / "browser-profile"
NOVNC_PROXY_CANDIDATES = ("novnc_proxy", "/usr/share/novnc/utils/novnc_proxy")
DEFAULT_TIMEOUT = 15 * 60
AUTOMATED_TIMEOUT = 90
LOGIN_REJECTED_TEXT = "please enter valid email address and password"


class RemoteLoginError(RuntimeError):
    """Raised when a browser login session cannot be completed."""


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _prepare_profile() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.chmod(0o700)


def _save_context_cookies(context) -> None:
    """Persist the browser's complete Midtown cookie objects.

    Keep the Playwright export shape so domain/path/security attributes are not
    lost. The HTTP client also accepts this list-shaped session format.
    """
    cookies = [
        cookie
        for cookie in context.cookies([urljoin(BASE_URL, "/ord-contents")])
        if "midtowncomics.com" in cookie.get("domain", "").lstrip(".").lower()
    ]
    if not cookies:
        raise RemoteLoginError("Authenticated browser context did not contain Midtown cookies")
    save_session(cookies)


def _looks_like_login(html: str) -> bool:
    lowered = html.lower()
    return 'name="txtpassword"' in lowered or "name='txtpassword'" in lowered


def _context_is_authenticated(context) -> bool:
    response = context.request.post(urljoin(BASE_URL, "/ord-contents"), timeout=30_000)
    return "/login" not in response.url.rstrip("/").lower() and not _looks_like_login(response.text())


def _save_validated_context_cookies(context) -> bool:
    """Persist cookies only after the authenticated orders endpoint succeeds."""
    if not _context_is_authenticated(context):
        return False
    _save_context_cookies(context)
    return True


def _is_authenticated(page) -> bool:
    """Return True only after Midtown redirects to the authenticated account page."""
    url = page.url.rstrip("/").lower().split("?", 1)[0]
    return url == f"{BASE_URL}/account-settings"

def _authenticated_page(context):
    """Find an authenticated Midtown tab among all restored browser pages."""
    for candidate in context.pages:
        if _is_authenticated(candidate):
            return candidate
    return None


def _desktop_user_agent(playwright) -> str:
    """Return Chromium's real UA without the "HeadlessChrome" token.

    reCAPTCHA v3 scores headless-labelled browsers lower; the version stays
    consistent with the installed Chromium.
    """
    browser = playwright.chromium.launch(headless=True)
    try:
        return browser.new_page().evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
    finally:
        browser.close()


def run_automated_login() -> None:
    """Authenticate with locally stored credentials using a headless browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RemoteLoginError("Install browser support with: python -m pip install -e '.[browser]'") from exc

    email, password = read_credentials()
    _prepare_profile()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=True,
            user_agent=_desktop_user_agent(playwright),
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            if _save_validated_context_cookies(context):
                return

            # The submit handler (deferred by Cloudflare Rocket Loader) fetches the
            # reCAPTCHA v3 token; submitting before it is attached posts an empty token.
            page.wait_for_function("() => window.grecaptcha && window.jQuery", timeout=AUTOMATED_TIMEOUT * 1000)
            page.fill("#txtEmail", email)
            page.fill("#txtPassword", password)
            page.evaluate("document.querySelector('#chkRemember').checked = true")
            with page.expect_navigation(timeout=AUTOMATED_TIMEOUT * 1000):
                page.click("#btnLogin")

            if LOGIN_REJECTED_TEXT in page.inner_text("body").lower():
                raise RemoteLoginError("Midtown rejected the email/password; check MIDTOWN_EMAIL and MIDTOWN_PASSWORD in .env")
            if not _save_validated_context_cookies(context):
                raise RemoteLoginError(f"Automated Midtown login did not authenticate (landed on {page.url})")
        finally:
            context.close()


def _ngrok_url(timeout: int = 30) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as response:
                import json

                tunnels = json.loads(response.read().decode()).get("tunnels", [])
                for tunnel in tunnels:
                    url = tunnel.get("public_url", "")
                    if url.startswith("https://"):
                        return url
        except (OSError, ValueError):
            time.sleep(0.5)
    raise RemoteLoginError("ngrok did not expose a public HTTPS URL in time")


def run_remote_login(timeout: int = DEFAULT_TIMEOUT) -> None:
    """Start an interactive remote login and wait until the profile is authenticated."""
    novnc_proxy = next((candidate for candidate in NOVNC_PROXY_CANDIDATES if _command_exists(candidate)), None)
    required = ["Xvfb", "x11vnc", "ngrok"]
    missing = [command for command in required if not _command_exists(command)]
    if novnc_proxy is None:
        missing.append("novnc_proxy (/usr/share/novnc/utils/novnc_proxy)")
    if missing:
        raise RemoteLoginError("Missing remote-login dependencies: " + ", ".join(missing))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RemoteLoginError("Install browser support with: python -m pip install -e '.[browser]'") from exc

    _prepare_profile()
    display = f":{100 + secrets.randbelow(100)}"
    env = os.environ.copy()
    env["DISPLAY"] = display
    processes: list[subprocess.Popen] = []

    def start(command: list[str], **kwargs):
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)
        processes.append(process)
        return process

    try:
        start(["Xvfb", display, "-screen", "0", "1440x1000x24", "-nolisten", "tcp"])
        time.sleep(1)
        start(["x11vnc", "-display", display, "-nopw", "-localhost", "-forever", "-shared", "-rfbport", "5900", "-quiet"])
        start([novnc_proxy, "--vnc", "127.0.0.1:5900", "--listen", "6080", "--web", "/usr/share/novnc"])
        time.sleep(1)
        start(["ngrok", "http", "6080"])
        public_url = _ngrok_url()
        login_link = public_url.rstrip("/") + "/vnc.html?autoconnect=true&resize=remote"

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=False,
                env=env,
                viewport={"width": 1440, "height": 900},
            )
            authenticated = _authenticated_page(context)
            if authenticated is None:
                page = context.new_page()
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            else:
                page = authenticated
            print(login_link, flush=True)

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                authenticated = _authenticated_page(context)
                # The account page is the authoritative browser signal here.
                # Some Midtown AJAX endpoints redirect to /login when called
                # outside their normal page flow even though the browser session
                # is authenticated and the account page is fully available.
                if _save_validated_context_cookies(context):
                    context.close()
                    return
                time.sleep(5)
            raise RemoteLoginError("Remote login timed out before Midtown authentication completed")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

