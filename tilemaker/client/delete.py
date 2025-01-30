"""
Deletion of various data structures from the database.
"""

from rich.console import Console

from tilemaker import orm


def delete_one_by_id(id: int, model) -> None:
    """
    Delete a single row from the database by ID.
    """
    from sqlmodel import select

    from tilemaker import database as db

    with db.get_session() as session:
        stmt = select(model).where(model.id == id)
        result = session.exec(stmt).one_or_none()

        if result is None:
            raise ValueError(f"{model.__name__} with ID {id} not found.")

        session.delete(result)
        session.commit()

    return


def delete_band(id: int, console: Console) -> None:
    """
    Delete a band from the database.
    """
    try:
        delete_one_by_id(id, orm.Band)
    except ValueError:
        console.print(f"Band with ID {id} not found.")

    console.print(f"Band with ID {id} deleted.")


def delete_catalog(id: int, console: Console) -> None:
    """
    Delete a catalog from the database.
    """
    try:
        delete_one_by_id(id, orm.SourceList)
    except ValueError:
        console.print(f"Catalog with ID {id} not found.")

    console.print(f"Catalog with ID {id} deleted.")


def delete_map(id: int, console: Console) -> None:
    """
    Delete a map from the database.
    """
    try:
        delete_one_by_id(id, orm.Map)
    except ValueError:
        console.print(f"Map with ID {id} not found.")

    console.print(f"Map with ID {id} deleted.")


def delete_box(id: int, console: Console) -> None:
    """
    Delete a box from the database.
    """
    try:
        delete_one_by_id(id, orm.HighlightBox)
    except ValueError:
        console.print(f"Box with ID {id} not found.")

    console.print(f"Box with ID {id} deleted.")
