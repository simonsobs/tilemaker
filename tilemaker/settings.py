"""
Settings for the project.
"""

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    "SQLAlchemy-appropriate database URL."

    origins: list[str] | None = None
    add_cors: bool = False
    "Settings for managng CORS middleware; useful for development."

    static_directory: str | None = "./static"
    "Static directory to serve the SPA from. Defaults to a version of the simonsobs/tileviewer UI."
    "See https://github.com/simonsobs/tileviewer"

    api_endpoint: str = "./"
    "The location of the API endpoint. Default assumes from the same place as the server."

    class Config:
        env_prefix = "TILEMAKER_"

settings = Settings()
