"""
CLI components (using typer)
"""

from pathlib import Path

import typer
from rich.console import Console

from . import simple

CONSOLE = Console()

APP = typer.Typer()


@APP.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """
    Start the development/user-hosted server for tilemaker.
    """
    from uvicorn import run

    from tilemaker.server import app

    run(app, host=host, port=port)


@APP.command()
def dev(host: str = "127.0.0.1", port: int = 8000):
    """
    Start the development server with a sample map for tilemaker.
    """

    import os

    from uvicorn import run

    from tilemaker.metadata.core import DataConfiguration
    from tilemaker.server import app

    app.config = DataConfiguration(
        map_groups=simple.add_sample_map(),
        source_groups=simple.add_sample_source_list(),
        boxes=simple.add_sample_box(),
    )

    run(app, host=host, port=port)

    # Cleanup
    os.remove("example.fits")


@APP.command()
def open(filenames: list[Path], host: str = "127.0.0.1", port: int = 8000):
    """
    Start the development/user-hosted server for tilemaker.
    """
    from uvicorn import run

    from tilemaker.metadata.generation import generate
    from tilemaker.server import app

    app.config = generate(filenames)

    run(app, host=host, port=port)


@APP.command()
def genconfig(filenames: list[Path], output: Path = Path("./generated_config.json")):
    """
    Start the development/user-hosted server for tilemaker.
    """
    from tilemaker.metadata.generation import generate

    generated_config = generate(filenames)

    with output.open("w") as handle:
        handle.write(generated_config.model_dump_json(indent=2))


def main():
    global APP

    APP()
