"""
Settings for the project.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"

settings = Settings()
