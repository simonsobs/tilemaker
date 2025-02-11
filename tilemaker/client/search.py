"""
Core functions for searching for individual components that can be deleted.
"""

from rich.console import Console
from sqlalchemy.orm import subqueryload

from tilemaker import orm


def select_all(model, load_children=None):
    from sqlmodel import select

    from tilemaker import database as db

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
                "quantity": band.quantity,
                "units": band.units,
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


def print_boxes(console: Console):
    """
    Print all boxes in the database.
    """
    boxes = select_all(orm.HighlightBox)

    console.print(f"Found {len(boxes)} boxes:")

    for box in boxes:
        console.print(
            {
                "id": box.id,
                "name": box.name,
                "description": box.description,
                "top_left_ra": box.top_left_ra,
                "top_left_dec": box.top_left_dec,
                "bottom_right_ra": box.bottom_right_ra,
                "bottom_right_dec": box.bottom_right_dec,
            }
        )
