"""
Start the development/user-hosted server for tilemaker.
"""

from pydantic_settings import BaseSettings, CliApp
from uvicorn import run

from tilemaker.server import app


class RunSettings(BaseSettings):
    """
    Settings for running the server for the tilemaker.
    """

    host: str = "127.0.0.1"
    port: int = 8000

    class Config:
        env_prefix = "TILEMAKER_"

    def cli_cmd(self) -> None:
        run(app, host=self.host, port=self.port)


def main():
    CliApp.run(RunSettings)
