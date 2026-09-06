"""OAuth2 authorization flows for Whoop and Oura."""

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import TOKENS_PATH, Settings


def _load_tokens() -> dict:
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    return {}


def _save_tokens(tokens: dict) -> None:
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))


def _capture_auth_code(port: int) -> str | None:
    """Start a temporary HTTP server to capture the OAuth callback."""
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            if "code" in qs:
                captured["code"] = qs["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Authorization successful! You can close this tab.</h2>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No authorization code received.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("localhost", port), Handler)
    server.timeout = 120
    server.handle_request()
    server.server_close()
    return captured.get("code")


def authorize_whoop(settings: Settings) -> dict:
    """Run OAuth2 flow for Whoop and return tokens."""
    cfg = settings.whoop
    state = secrets.token_urlsafe(16)

    auth_params = urlencode({
        "client_id": cfg.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": cfg.scopes,
        "state": state,
    })
    auth_url = f"{cfg.auth_url}?{auth_params}"

    print(f"\nOpening Whoop authorization in browser...\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = _capture_auth_code(settings.oauth_redirect_port)
    if not code:
        raise RuntimeError("Failed to capture Whoop authorization code")

    resp = httpx.post(cfg.token_url, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    })
    resp.raise_for_status()
    return resp.json()


def authorize_oura(settings: Settings) -> dict:
    """Run OAuth2 flow for Oura and return tokens."""
    cfg = settings.oura
    state = secrets.token_urlsafe(16)

    auth_params = urlencode({
        "client_id": cfg.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": cfg.scopes,
        "state": state,
    })
    auth_url = f"{cfg.auth_url}?{auth_params}"

    print(f"\nOpening Oura authorization in browser...\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = _capture_auth_code(settings.oauth_redirect_port)
    if not code:
        raise RuntimeError("Failed to capture Oura authorization code")

    resp = httpx.post(cfg.token_url, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    })
    resp.raise_for_status()
    return resp.json()


def refresh_token(provider: str, refresh_tok: str, settings: Settings) -> dict:
    """Refresh an expired access token."""
    if provider == "whoop":
        cfg = settings.whoop
    elif provider == "oura":
        cfg = settings.oura
    else:
        raise ValueError(f"Unknown provider: {provider}")

    resp = httpx.post(cfg.token_url, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    })
    resp.raise_for_status()
    return resp.json()


def get_tokens(provider: str) -> dict | None:
    """Load saved tokens for a provider."""
    all_tokens = _load_tokens()
    return all_tokens.get(provider)


def save_provider_tokens(provider: str, tokens: dict) -> None:
    """Save tokens for a provider."""
    all_tokens = _load_tokens()
    all_tokens[provider] = tokens
    _save_tokens(all_tokens)


if __name__ == "__main__":
    settings = Settings()
    print("=== Biometrics OAuth Setup ===\n")

    choice = input("Connect: [1] Whoop  [2] Oura  [3] Both: ").strip()

    if choice in ("1", "3"):
        tokens = authorize_whoop(settings)
        save_provider_tokens("whoop", tokens)
        print("Whoop connected!")

    if choice in ("2", "3"):
        tokens = authorize_oura(settings)
        save_provider_tokens("oura", tokens)
        print("Oura connected!")

    print("\nDone. Tokens saved to tokens.json")
