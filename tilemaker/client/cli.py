"""
CLI components (using typer)
"""

import typer
from tilemaker import orm
from rich.console import Console
from pathlib import Path

from . import search
from . import delete
from . import add

CONSOLE = Console()

APP = typer.Typer()

list_app = typer.Typer(help="Commands for listing products in the database")
APP.add_typer(list_app, name="list")

delete_app = typer.Typer(help="Remove (irrevocably) products from the database")
APP.add_typer(delete_app, name="delete")

add_app = typer.Typer(help="Add products to the database")
APP.add_typer(add_app, name="add")



@add_app.command("catalog")
def add_catalog(catalog: str, name: str, description: str):
    """
    Add a catalog to the database.
    """
    
    global CONSOLE

    add.add_catalog(catalog, name, description, CONSOLE)


@add_app.command("iqu", help="Add an IQU map to the database (FITS)")
def add_iqu(
    filename: Path,
    map_name: str,
    description: str = "No description provided",
    intensity_only: bool = False,
    telescope: str = "",
    data_release: str = "",
    season: str = "",
    tags: str = "",
    patch: str = "",
    frequency: str = "",
    units: str = ""
):
    """
    Add an IQU map to the database.
    """

    global CONSOLE

    add.add_fits_map(
        filename,
        map_name,
        CONSOLE,
        description,
        intensity_only,
        telescope if telescope else None,
        data_release if data_release else None,
        season if season else None,
        tags if tags else None,
        patch if patch else None,
        frequency if frequency else None,
        units if units else None
    )



@delete_app.command("map")
def delete_map(id: int):
    """
    Delete a map from the database.
    """

    global CONSOLE

    delete.delete_map(id, CONSOLE)

@delete_app.command("band")
def delete_band(id: int):
    """
    Delete a band from the database.
    """

    global CONSOLE

    delete.delete_band(id, CONSOLE)


@delete_app.command("catalog")
def delete_catalog(id: int):
    """
    Delete a catalog from the database.
    """

    global CONSOLE

    delete.delete_catalog(id, CONSOLE)


@list_app.command("bands")
def list_bands():
    """
    List all bands in the database.
    """

    global CONSOLE

    search.print_bands(CONSOLE)

@list_app.command("maps")
def list_maps():
    """
    List all maps in the database.
    """

    global CONSOLE

    search.print_maps(CONSOLE)


@list_app.command("catalogs")
def list_catalogs():
    """
    List all maps in the database.
    """
    
    global CONSOLE

    search.print_catalogs(CONSOLE)
   

@APP.command()
def serve(host: str="127.0.0.1", port: int=8000):
    """
    Start the development/user-hosted server for tilemaker.
    """
    from uvicorn import run

    from tilemaker.server import app

    run(app, host=host, port=port)


def main():
    global APP

    APP()