"""
Settings for the project.
"""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./tilemaker.db"
    "SQLAlchemy-appropriate database URL."

    origins: list[str] | None = ["*"]
    add_cors: bool = True
    "Settings for managng CORS middleware; useful for development."

    serve_frontend: bool = True
    "Whether to serve the frontend. If False, the frontend must be served elsewhere; useful for large deployments or development."

    api_endpoint: str = "./"
    "The location of the API endpoint. Default assumes from the same place as the server."

    use_in_memory_cache: bool = True
    "Use an in-memory cache for the tiles. Can improve performance by reducing database queries."

    proprietary_scope: str = "simonsobs"
    "The scope to require for proprietary data access."

    auth_type: Literal["soauth", "mock"] = "mock"
    "The authentication type to use."

    # SOAuth settings (if used)
    soauth_base_url: str | None = None
    soauth_auth_url: str | None = None
    soauth_app_id: str | None = None
    soauth_client_secret: str | None = None
    soauth_public_key: str | None = None
    soauth_key_pair_type: str | None = None

    class Config:
        env_prefix = "TILEMAKER_"


settings = Settings()
