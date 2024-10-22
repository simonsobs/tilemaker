"""
Settings for the project.
"""

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

    class Config:
        env_prefix = "TILEMAKER_"


settings = Settings()
