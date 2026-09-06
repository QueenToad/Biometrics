"""Check the local setup and report what is wrong, without printing secrets.

Run: python -m src.doctor
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import ValidationError

from .config import TOKENS_PATH, Settings

ENV_PATH = Path(__file__).parent.parent / ".env"
OK, BAD, WARN = "  ok  ", " FAIL ", " warn "


def _mask(value: Optional[str]) -> str:
    """Describe a secret well enough to debug it, without revealing it."""
    if value is None:
        return "not set"
    if value == "":
        return "EMPTY"
    shape = f"len={len(value)}"
    if value != value.strip():
        shape += ", HAS SURROUNDING WHITESPACE"
    if any(c in value for c in "\"'"):
        shape += ", CONTAINS QUOTES"
    if " " in value.strip():
        shape += ", CONTAINS A SPACE"
    return f"{shape}, {value[:3]}…{value[-3:]}"


def check_env_file() -> List[Tuple[str, str]]:
    """Find lines python-dotenv cannot read, and say why."""
    out = []
    if not ENV_PATH.exists():
        return [(BAD, f".env not found at {ENV_PATH}")]

    raw = ENV_PATH.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        out.append((BAD, ".env starts with a UTF-8 BOM — it breaks the first line"))
    if b"\r\n" in raw:
        out.append((WARN, ".env has Windows line endings (CRLF)"))

    for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            out.append((BAD, f"line {n}: no '=' — dotenv will skip it: {stripped[:30]!r}"))
            continue
        key = stripped.split("=", 1)[0]
        if key != key.strip():
            out.append((BAD, f"line {n}: whitespace before '=' in {key!r}"))
        elif not key.replace("_", "").isalnum():
            out.append((BAD, f"line {n}: odd characters in key {key!r}"))

    if not out:
        out.append((OK, ".env parses cleanly"))
    return out


def check_credentials(settings: Settings, provider: str) -> Tuple[str, str]:
    """Ask the provider whether the id+secret pair alone is valid.

    The client_credentials grant authenticates the client and nothing else, so
    it separates "these credentials are wrong" from every other reason an
    authorization-code exchange can fail. A server that refuses the grant type
    still had to authenticate us first, so unsupported_grant_type is a pass.
    """
    import httpx

    cfg = getattr(settings, provider)
    try:
        resp = httpx.post(
            cfg.token_url,
            data={"grant_type": "client_credentials", "client_id": cfg.client_id,
                  "client_secret": cfg.client_secret},
            timeout=20,
        )
    except Exception as exc:
        return WARN, f"{provider}: could not reach {cfg.token_url} ({exc})"

    if resp.status_code < 400:
        return OK, f"{provider}: credentials accepted by {cfg.token_url}"

    error = ""
    try:
        error = resp.json().get("error", "")
    except ValueError:
        pass

    if error in ("unsupported_grant_type", "invalid_grant", "invalid_scope",
                 "unauthorized_client"):
        return OK, (f"{provider}: credentials accepted (server refused the grant "
                    f"type itself: {error}) — the id and secret are good")
    if error == "invalid_client":
        return BAD, (f"{provider}: the server rejects this id+secret pair.\n"
                     f"       Regenerate the secret in the provider's dashboard, "
                     f"or create a fresh app.")
    return WARN, f"{provider}: unexpected {resp.status_code} — {resp.text[:120]}"


def main(online: bool = False) -> int:
    print(f"\n=== .env ({ENV_PATH}) ===")
    problems = 0
    for status, msg in check_env_file():
        print(f"{status} {msg}")
        problems += status == BAD

    print("\n=== credentials as loaded ===")
    try:
        settings = Settings()
    except ValidationError as exc:
        # A missing variable makes Settings unbuildable — which is exactly when
        # this report matters, so name the fields instead of dying here.
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"])
            print(f"{BAD} {field}: {err['msg']} — dotenv never saw this line")
        print(f"\n{problems + len(exc.errors())} problem(s) found.")
        print("Fix .env first, then run this again.")
        return 1

    for provider in ("whoop", "oura"):
        cfg = getattr(settings, provider)
        print(f"  {provider}")
        print(f"    client_id     : {_mask(cfg.client_id)}")
        print(f"    client_secret : {_mask(cfg.client_secret)}")
        print(f"    redirect_uri  : {settings.redirect_uri_for(provider)}")
        for field, value in (("client_id", cfg.client_id), ("client_secret", cfg.client_secret)):
            if not (value or "").strip():
                print(f"{BAD} {provider}.{field} is empty")
                problems += 1
            elif value != value.strip():
                print(f"{BAD} {provider}.{field} has stray whitespace — retype it in .env")
                problems += 1

        # The classic paste error: the id copied into the secret field. The
        # provider then rejects the exchange with 401 invalid_client, which
        # doesn't hint at which of the two values is wrong.
        if cfg.client_id and cfg.client_id == cfg.client_secret:
            print(f"{BAD} {provider}: client_secret is identical to client_id — "
                  "copy the secret from the provider's dashboard")
            problems += 1

    notion = settings.notion
    print("  notion")
    print(f"    token         : {_mask(notion.token)}")
    print(f"    parent_page   : {notion.parent_page_id or 'not set'}")

    print(f"\n=== tokens ({TOKENS_PATH}) ===")
    if not TOKENS_PATH.exists():
        print(f"{WARN} no tokens yet — run: python -m src.auth both")
    else:
        saved = json.loads(TOKENS_PATH.read_text())
        for provider in ("whoop", "oura"):
            entry = saved.get(provider)
            if not entry:
                print(f"{WARN} {provider}: not connected — run: python -m src.auth {provider}")
            elif not entry.get("refresh_token"):
                print(f"{BAD} {provider}: no refresh token, it will expire within the hour")
                print(f"       re-authorize: python -m src.auth {provider}")
                problems += 1
            else:
                print(f"{OK} {provider}: connected, renewable")

    if online:
        print("\n=== credentials checked against the provider ===")
        for provider in ("whoop", "oura"):
            status, msg = check_credentials(settings, provider)
            print(f"{status} {msg}")
            problems += status == BAD
    else:
        print("\n(run with --online to ask each provider whether its "
              "credentials are valid)")

    print(f"\n{problems} problem(s) found." if problems else "\nAll good.")
    return 1 if problems else 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(online="--online" in sys.argv))
