"""Credential and session storage helpers."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("MIDTOWN_CONFIG_DIR", Path.home() / ".config" / "midtown-comics"))
CREDENTIALS_FILE = CONFIG_DIR / "credentials"
COOKIES_FILE = CONFIG_DIR / "cookies.json"
SESSION_FILE = CONFIG_DIR / "session.json"
# ponytail: .env at the project root (editable install); MIDTOWN_ENV_FILE overrides it.
ENV_FILE = Path(os.environ.get("MIDTOWN_ENV_FILE", Path(__file__).resolve().parent.parent / ".env"))


def _read_key_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def read_credentials(interactive: bool = True) -> tuple[str, str]:
    email = os.getenv("MIDTOWN_EMAIL")
    password = os.getenv("MIDTOWN_PASSWORD")
    if email and password:
        return email, password
    for path in (ENV_FILE, CREDENTIALS_FILE):
        if path.exists():
            values = _read_key_values(path)
            if values.get("MIDTOWN_EMAIL") and values.get("MIDTOWN_PASSWORD"):
                return values["MIDTOWN_EMAIL"], values["MIDTOWN_PASSWORD"]
    if interactive:
        return input("Email: ").strip(), getpass.getpass("Password: ")
    raise RuntimeError(f"Midtown credentials not found; set MIDTOWN_EMAIL and MIDTOWN_PASSWORD in {ENV_FILE}")


def save_credentials(email: str, password: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(
        f"MIDTOWN_EMAIL={email}\nMIDTOWN_PASSWORD={password}\n",
        encoding="utf-8",
    )
    CREDENTIALS_FILE.chmod(0o600)


def save_session(cookies: dict | list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps({"cookies": cookies}, indent=2) + "\n")
    SESSION_FILE.chmod(0o600)


def _valid_cookie(item: dict) -> bool:
    domain = str(item.get("domain", "")).lstrip(".").lower()
    return "midtowncomics.com" in domain and bool(item.get("name"))


def load_session_cookies() -> list[dict]:
    """Load Midtown cookies while preserving browser scope/security metadata."""
    cookies: dict[tuple[str, str, str], dict] = {}

    if COOKIES_FILE.exists():
        data = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        items = data.get("cookies", []) if isinstance(data, dict) else data
        for item in items:
            if _valid_cookie(item):
                key = (item["name"], item.get("domain", ""), item.get("path", "/"))
                cookies[key] = item

    if SESSION_FILE.exists():
        refreshed = json.loads(SESSION_FILE.read_text(encoding="utf-8")).get("cookies", {})
        if isinstance(refreshed, list):
            for item in refreshed:
                if _valid_cookie(item):
                    key = (item["name"], item.get("domain", ""), item.get("path", "/"))
                    cookies[key] = item
        else:
            for name, value in refreshed.items():
                cookies[(name, "", "/")] = {"name": name, "value": value, "path": "/"}

    return list(cookies.values())


def load_session() -> dict:
    """Load cookies as a name/value mapping for backwards compatibility."""
    result = {}
    for item in load_session_cookies():
        if item.get("path", "/") == "/" or item["name"] not in result:
            result[item["name"]] = item.get("value", "")
    return result
