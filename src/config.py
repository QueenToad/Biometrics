from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

TOKENS_PATH = Path(__file__).parent.parent / "tokens.json"


class WhoopConfig(BaseSettings):
    client_id: str = Field(alias="WHOOP_CLIENT_ID")
    client_secret: str = Field(alias="WHOOP_CLIENT_SECRET")
    auth_url: str = "https://api.prod.whoop.com/oauth/oauth2/auth"
    token_url: str = "https://api.prod.whoop.com/oauth/oauth2/token"
    api_base: str = "https://api.prod.whoop.com/developer"
    scopes: str = "read:recovery read:sleep read:workout read:profile read:body_measurement"


class OuraConfig(BaseSettings):
    client_id: str = Field(alias="OURA_CLIENT_ID")
    client_secret: str = Field(alias="OURA_CLIENT_SECRET")
    auth_url: str = "https://cloud.ouraring.com/oauth/authorize"
    token_url: str = "https://api.ouraring.com/oauth/token"
    api_base: str = "https://api.ouraring.com/v2"
    scopes: str = "daily heartrate personal workout tag session spo2"


class Settings(BaseSettings):
    oauth_redirect_port: int = Field(default=8080, alias="OAUTH_REDIRECT_PORT")
    whoop: WhoopConfig = WhoopConfig()
    oura: OuraConfig = OuraConfig()

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.oauth_redirect_port}/callback"
