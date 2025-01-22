"""
Core functions for searching for individual components that can be deleted.
"""

from rich.console import Console
from tilemaker import orm
from sqlalchemy.orm import subqueryload

def select_all(model, load_children=None):
    from tilemaker import database as db
    from sqlmodel import select

    with db.get_session() as session:
        if load_children is not None:
            stmt = select(model).options(subqueryload(load_children))
        else:
            stmt = select(model)
        results = session.exec(stmt).all()

    return results


def get_bands() -> list[orm.Band]:
    """
    Get all bands from the database.
    """
    return select_all(orm.Band, orm.Band.map)


def get_catalogs() -> list[orm.SourceList]:
    """
    Get all catalogs from the database.
    """
    return select_all(orm.SourceList, orm.SourceList.sources)


def get_maps() -> list[orm.Map]:
    """
    Get all maps from the database.
    """
    return select_all(orm.Map, orm.Map.bands)


def print_bands(console: Console):
    """
    Print all bands in the database.
    """
    bands = get_bands()

    console.print(f"Found {len(bands)} bands:")

    for band in bands:
        console.print(
            {
                "id": band.id,
                "map": band.map.name,
                "levels": band.levels,
                "tile_size": band.tile_size,
            }
        )

def print_maps(console: Console):
    """
    Print all maps in the database.
    """
    maps = get_maps()

    console.print(f"Found {len(maps)} maps:")

    for map in maps:
        console.print(
            {
                "id": map.id,
                "name": map.name,
                "description": map.description,
                "telescope": map.telescope,
                "data_release": map.data_release,
                "season": map.season,
                "tags": map.tags,
                "patch": map.patch,
                "bands": len(map.bands),
                "levels": [band.levels for band in map.bands],
            }
        )


def print_catalogs(console: Console):
    """
    Print all catalogs in the database.
    """
    catalogs = get_catalogs()

    console.print(f"Found {len(catalogs)} catalogs:")

    for catalog in catalogs:
        console.print(
            {
                "id": catalog.id,
                "name": catalog.name,
                "description": catalog.description,
                "source_count": len(catalog.sources),
            }
        )