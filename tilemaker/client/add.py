"""
Add various data structures to the database.
"""

from tilemaker import orm
from pydantic import BaseModel, TypeAdapter
from rich.console import Console
from pathlib import Path

def _add_catalog_csv(filename: str, name: str, description: str, console: Console):
    import numpy as np

    from tilemaker import database as db

    data = np.loadtxt(filename, delimiter=",", skiprows=1)

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

        console.print(f"Catalog succesfully added (id: {catalog.id}).")

    return


class CatalogIngestItem(BaseModel):
    flux: float
    ra: float
    dec: float
    name: str | None = None


def _add_catalog_json(filename: str, name: str, description: str, console: Console):
    """
    De-serialize a JSON file into a catalog.
    """
    from tilemaker import database as db

    with open(filename, "r") as f:
        data = TypeAdapter(list[CatalogIngestItem]).validate_json(f.read())

    db.create_database_and_tables()
    with db.get_session() as session:
        catalog = orm.SourceList(name=name, description=description)
        session.add(catalog)

        items = [
            orm.SourceItem(
                source_list=catalog, flux=item.flux, ra=item.ra, dec=item.dec, name=item.name
            )
            for item in data
        ]
        session.add_all(items)

        session.commit()

        console.print(f"Catalog succesfully added (id: {catalog.id}).")

    return


def add_catalog(filename: str, name: str, description: str, console: Console):
    """
    Add a catalog to the database.
    """

    if filename.endswith(".csv"):
        _add_catalog_csv(filename, name, description, console)
    elif filename.endswith(".json"):
        _add_catalog_json(filename, name, description, console)
    else:
        console.print("Catalog must be a CSV or JSON file")

    return



def add_fits_map(
    filename: Path,
    map_name: str,
    console: Console,
    description: str = "No description provided",
    intensity_only: bool = False,
    telescope: str | None = None,
    data_release: str | None = None,
    season: str | None = None,
    tags: str | None = None,
    patch: str | None = None,
    frequency: str | None = None,
    units: str | None = None
):
    QUANTITY_MAP = {
        "uK": "T",
        "K": "T",
    }

    BOUNDS_MAP = {
        "uK": (-500.0, 500.0),
        "K": (-5e-4, 5e-4),
    }
    
    import numpy as np

    import tilemaker.database as db
    import tilemaker.orm
    from tilemaker.processing.fits_simple import FITSFile, LayerTree

    db.create_database_and_tables()

    fits_file = FITSFile(filename=filename)
    map_name = map_name
    description = description

    with db.get_session() as session:
        add = []

        if (map_metadata := session.get(tilemaker.orm.Map, map_name)) is None:
            telescope = (
                telescope
                if telescope is not None
                else fits_file.individual_trees[0].header.get("TELESCOP", None)
            )
            data_release = (
                data_release
                if data_release is not None
                else fits_file.individual_trees[0].header.get("RELEASE", None)
            )
            season = (
                season
                if season is not None
                else fits_file.individual_trees[0].header.get("SEASON", None)
            )
            tags = (
                tags
                if tags is not None
                else fits_file.individual_trees[0].header.get("ACTTAGS", None)
            )
            patch = (
                patch
                if patch is not None
                else fits_file.individual_trees[0].header.get("PATCH", None)
            )
            units = (
                units
                if units is not None
                else fits_file.individual_trees[0].header.get("BUNIT", None)
            )

            map_metadata = tilemaker.orm.Map(
                name=map_name,
                description=description,
                telescope=telescope,
                data_release=data_release,
                season=season,
                tags=tags,
                patch=patch,
            )

            add.append(map_metadata)

            console.print("Found map:", map_metadata)
        else:
            console.print(f"Map {map_name} already exists in the database")
            return

        for fits_image in fits_file.individual_trees:
            if intensity_only and fits_image.identifier != "I":
                continue

            tile_size = fits_image.tile_size
            number_of_layers = fits_image.number_of_levels

            tree = LayerTree(
                number_of_layers=number_of_layers,
                image_pixel_size=tile_size,
                image=fits_image,
            )

            top_right, bottom_left = fits_image.world_size_degrees()

            frequency = (
                frequency
                if frequency is not None
                else fits_image.header.get("FREQ", "f000").replace("f", "")
            )

            lower_bound, upper_bound = BOUNDS_MAP.get(units, [-500.0, 500.0])

            band = tilemaker.orm.Band(
                map=map_metadata,
                tiles_available=True,
                levels=number_of_layers,
                tile_size=tile_size,
                frequency=frequency,
                stokes_parameter=str(fits_image.identifier),
                units=units,
                recommended_cmap_min=lower_bound,
                recommended_cmap_max=upper_bound,
                recommended_cmap="RdBu_r",
                bounding_left=bottom_left[0].value,
                bounding_right=top_right[0].value,
                bounding_top=top_right[1].value,
                bounding_bottom=bottom_left[1].value,
                quantity=QUANTITY_MAP.get(
                    units, None
                ),
            )

            console.print("Ingesting:", band)

            H, edges = fits_image.histogram_raw_data(
                n_bins=128, min=lower_bound * 4, max=upper_bound * 4
            )

            histogram = tilemaker.orm.Histogram(
                band=band,
                start=lower_bound * 4,
                end=upper_bound * 4,
                bins=128,
                edges_data_type=str(edges.dtype),
                edges=edges.tobytes(order="C"),
                histogram_data_type=str(H.dtype),
                histogram=H.tobytes(order="C"),
            )

            tile_metadata = []

            for depth in range(number_of_layers):
                n_tiles_x = 2 ** (depth + 1)
                n_tiles_y = 2 ** (depth)

                for x in range(n_tiles_x):
                    for y in range(n_tiles_y):
                        tile_data = tree.get_tile(depth, x, y)

                        if isinstance(tile_data.data, np.ma.MaskedArray):
                            bytes = tile_data.data.tobytes(order="C", fill_value=np.nan)
                        elif tile_data.data is None:
                            bytes = None
                        else:
                            bytes = tile_data.data.tobytes(order="C")

                        tile_metadata.append(
                            tilemaker.orm.Tile(
                                level=depth,
                                x=x,
                                y=y,
                                band=band,
                                data=bytes,
                                data_type=str(tile_data.data.dtype)
                                if tile_data.data is not None
                                else None,
                            )
                        )

            add += [band, histogram] + tile_metadata

            session.add_all(add)
            session.commit()

            add = []