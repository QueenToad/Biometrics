from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

TOKENS_PATH = Path(__file__).parent.parent / "tokens.json"


class WhoopConfig(BaseSettings):
    client_id: str = Field(alias="WHOOP_CLIENT_ID")
    client_secret: str = Field(alias="WHOOP_CLIENT_SECRET")
    redirect_uri: Optional[str] = Field(default=None, alias="WHOOP_REDIRECT_URI")
    auth_url: str = "https://api.prod.whoop.com/oauth/oauth2/auth"
    token_url: str = "https://api.prod.whoop.com/oauth/oauth2/token"
    api_base: str = "https://api.prod.whoop.com/developer"
    scopes: str = "read:recovery read:sleep read:workout read:profile read:body_measurement"


class OuraConfig(BaseSettings):
    client_id: str = Field(alias="OURA_CLIENT_ID")
    client_secret: str = Field(alias="OURA_CLIENT_SECRET")
    redirect_uri: Optional[str] = Field(default=None, alias="OURA_REDIRECT_URI")
    auth_url: str = "https://cloud.ouraring.com/oauth/authorize"
    token_url: str = "https://api.ouraring.com/oauth/token"
    api_base: str = "https://api.ouraring.com/v2"
    scopes: str = "daily heartrate personal workout tag session spo2"


class Settings(BaseSettings):
    oauth_redirect_port: int = Field(default=8080, alias="OAUTH_REDIRECT_PORT")
    oauth_redirect_uri: Optional[str] = Field(default=None, alias="OAUTH_REDIRECT_URI")
    whoop: WhoopConfig = Field(default_factory=WhoopConfig)
    oura: OuraConfig = Field(default_factory=OuraConfig)

    @property
    def redirect_uri(self) -> str:
        """Default callback URL, used when a provider doesn't override it."""
        if self.oauth_redirect_uri:
            return self.oauth_redirect_uri
        return f"http://localhost:{self.oauth_redirect_port}/callback"

    def redirect_uri_for(self, provider: str) -> str:
        """The redirect URI registered with a given provider.

        Must match what the provider has on file character for character,
        or the OAuth exchange fails with redirect_uri_mismatch.
        """
        cfg = getattr(self, provider, None)
        if cfg is None:
            raise ValueError(f"Unknown provider: {provider}")
        return cfg.redirect_uri or self.redirect_uri
