"""
CLI components (using typer)
"""

import typer
from tilemaker import orm

APP = typer.Typer()

list_app = typer.Typer(help="Commands for listing products in the database")
APP.add_typer(list_app, name="list")

delete_app = typer.Typer(help="Remove (irrevocably) products from the database")
APP.add_typer(delete_app, name="delete")

add_app = typer.Typer(help="Add products to the database")
APP.add_typer(add_app, name="add")


def select_all(model):
    from tilemaker import database as db
    from sqlmodel import select

    with db.get_session() as session:
        stmt = select(model)
        results = session.exec(stmt).all()

    return results


@add_app.command("catalog")
def add_catalog(catalog: str, name: str, description: str):
    """
    Add a catalog to the database.
    """
    import numpy as np

    from tilemaker import database as db
    from tilemaker import orm

    data = np.loadtxt(catalog, delimiter=",", skiprows=1)

    db.create_database_and_tables()
    with db.get_session() as session:
        catalog = orm.SourceList(name=name, description=description)
        session.add(catalog)

        items = [
            orm.SourceItem(
                source_list=catalog, flux=row[0], ra=row[1], dec=row[2]
            )
            for row in data
        ]
        session.add_all(items)

        session.commit()

    print("Catalog successfully added.")


@delete_app.command("map")
def delete_map(id: int):
    """
    Delete a map from the database.
    """
    from tilemaker import database as db
    from tilemaker import orm
    from sqlmodel import select

    with db.get_session() as session:
        stmt = select(orm.Map).where(orm.Map.id == id)
        result = session.exec(stmt).one_or_none()

        if result is None:
            print(f"Map with ID {id} not found.")
            return

        session.delete(result)
        session.commit()

    print(f"Map with ID {id} deleted.")

@delete_app.command("band")
def delete_band(id: int):
    """
    Delete a band from the database.
    """
    from tilemaker import database as db
    from tilemaker import orm
    from sqlmodel import select

    with db.get_session() as session:
        stmt = select(orm.Band).where(orm.Band.id == id)
        result = session.exec(stmt).one_or_none()

        if result is None:
            print(f"Band with ID {id} not found.")
            return

        session.delete(result)
        session.commit()

    print(f"Band with ID {id} deleted.")

@delete_app.command("catalog")
def delete_catalog(id: int):
    """
    Delete a catalog from the database.
    """
    from tilemaker import database as db
    from tilemaker import orm
    from sqlmodel import select

    with db.get_session() as session:
        stmt = select(orm.SourceList).where(orm.SourceList.id == id)
        result = session.exec(stmt).one_or_none()

        if result is None:
            print(f"Catalog with ID {id} not found.")
            return

        session.delete(result)
        session.commit()

    print(f"Catalog with ID {id} deleted.")


@list_app.command("bands")
def list_bands():
    """
    List all bands in the database.
    """
    bands = select_all(orm.Band)

    for band in bands:
        print(band)

@list_app.command("maps")
def list_maps():
    """
    List all maps in the database.
    """
    maps = select_all(orm.Map)

    for map in maps:
        print(map)

@list_app.command("catalogs")
def list_catalogs():
    """
    List all maps in the database.
    """
    catalogs = select_all(orm.SourceList)

    for catalog in catalogs:
        print(catalog)

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