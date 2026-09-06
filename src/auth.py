"""OAuth2 authorization flows for Whoop and Oura."""

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import TOKENS_PATH, Settings

PROVIDERS = ("whoop", "oura")


def _load_tokens() -> dict:
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    return {}


def _save_tokens(tokens: dict) -> None:
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    TOKENS_PATH.chmod(0o600)


def get_tokens(provider: str) -> Optional[dict]:
    """Load saved tokens for a provider."""
    return _load_tokens().get(provider)


def save_provider_tokens(provider: str, tokens: dict) -> None:
    """Save tokens for a provider."""
    all_tokens = _load_tokens()
    all_tokens[provider] = tokens
    _save_tokens(all_tokens)


def _callback_port(redirect_uri: str, fallback: int) -> int:
    parsed = urlparse(redirect_uri)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else fallback


def _capture_auth_code(port: int, expected_state: str) -> str:
    """Serve the OAuth callback once and return the authorization code.

    Rejects a callback whose `state` doesn't match the one we sent, which is
    what stops an attacker from feeding us their own authorization code.
    """
    captured: Dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            code = qs.get("code", [None])[0]
            state = qs.get("state", [None])[0]
            error = qs.get("error", [None])[0]

            if error:
                captured["error"] = f"{error}: {qs.get('error_description', [''])[0]}"
                body = b"<h2>Authorization failed. Check the terminal.</h2>"
                status = 400
            elif not code:
                captured["error"] = "No authorization code in callback"
                body = b"<h2>No authorization code received.</h2>"
                status = 400
            elif not secrets.compare_digest(state or "", expected_state):
                captured["error"] = "State mismatch - possible CSRF, aborting"
                body = b"<h2>State mismatch. Authorization rejected.</h2>"
                status = 400
            else:
                captured["code"] = code
                body = b"<h2>Authorization successful! You can close this tab.</h2>"
                status = 200

            self.send_response(status)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("localhost", port), Handler)
    server.timeout = 120
    server.handle_request()
    server.server_close()

    if "error" in captured:
        raise RuntimeError(captured["error"])
    if "code" not in captured:
        raise RuntimeError("Timed out waiting for the OAuth callback")
    return captured["code"]


def _exchange_code(provider: str, code: str, redirect_uri: str, settings: Settings) -> dict:
    cfg = getattr(settings, provider)
    resp = httpx.post(cfg.token_url, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    })
    resp.raise_for_status()
    return resp.json()


def authorize(provider: str, settings: Settings) -> dict:
    """Run the OAuth2 authorization-code flow for a provider and return tokens."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")

    cfg = getattr(settings, provider)
    missing = [
        name for name, value in (
            (f"{provider.upper()}_CLIENT_ID", cfg.client_id),
            (f"{provider.upper()}_CLIENT_SECRET", cfg.client_secret),
        )
        if not (value or "").strip()
    ]
    if missing:
        # Without this the provider just answers 400 invalid_request in the
        # browser, which says nothing about the empty .env line behind it.
        raise RuntimeError(
            f"{', '.join(missing)} is empty in .env — fill it in before authorizing."
        )

    redirect_uri = settings.redirect_uri_for(provider)
    state = secrets.token_urlsafe(16)

    auth_url = f"{cfg.auth_url}?" + urlencode({
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg.scopes,
        "state": state,
    })

    print(f"\nOpening {provider} authorization in your browser:\n{auth_url}\n")
    webbrowser.open(auth_url)

    port = _callback_port(redirect_uri, settings.oauth_redirect_port)
    code = _capture_auth_code(port, state)
    return _exchange_code(provider, code, redirect_uri, settings)


def refresh_token(provider: str, refresh_tok: str, settings: Settings) -> dict:
    """Exchange a refresh token for a fresh access token."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")

    cfg = getattr(settings, provider)
    resp = httpx.post(cfg.token_url, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "scope": "offline",
    })
    resp.raise_for_status()
    return resp.json()


CHOICES = {
    "1": ["whoop"], "whoop": ["whoop"],
    "2": ["oura"], "oura": ["oura"],
    "3": ["whoop", "oura"], "both": ["whoop", "oura"],
}


def _pick(argv: List[str]) -> List[str]:
    """Read the provider from argv, falling back to a prompt.

    Taking it as an argument means pasting a block of commands can't feed the
    next line into the prompt by accident.
    """
    if argv:
        chosen = CHOICES.get(argv[0].strip().lower())
        if not chosen:
            raise SystemExit(f"Unknown provider {argv[0]!r}. Use: whoop, oura, or both.")
        return chosen
    return CHOICES.get(input("Connect: [1] Whoop  [2] Oura  [3] Both: ").strip().lower(), [])


if __name__ == "__main__":
    import sys

    settings = Settings()
    print("=== Biometrics OAuth Setup ===\n")

    selected = _pick(sys.argv[1:])
    if not selected:
        raise SystemExit("Pick 1, 2 or 3 — or run: python -m src.auth oura")

    for provider in selected:
        print(f"\nRedirect URI for {provider}: {settings.redirect_uri_for(provider)}")
        print("(this must match the one registered with the provider exactly)")
        tokens = authorize(provider, settings)
        save_provider_tokens(provider, tokens)
        print(f"{provider} connected.")

    print(f"\nDone. Tokens saved to {TOKENS_PATH}")
