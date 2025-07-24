"""
Add various data structures to the database.
"""

from pathlib import Path

from pydantic import BaseModel, TypeAdapter
from rich.console import Console

from tilemaker import orm


def _add_catalog_csv(
    filename: str,
    name: str,
    description: str,
    console: Console,
    proprietary: bool = False,
):
    import numpy as np

    from tilemaker import database as db

    data = np.loadtxt(filename, delimiter=",", skiprows=1)

    db.create_database_and_tables()
    with db.get_session() as session:
        catalog = orm.SourceList(
            name=name, description=description, proprietary=proprietary
        )
        session.add(catalog)

        items = [
            orm.SourceItem(
                source_list=catalog,
                flux=row[0],
                ra=row[1],
                dec=row[2],
                proprietary=proprietary,
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


def _add_catalog_json(
    filename: str,
    name: str,
    description: str,
    console: Console,
    proprietary: bool = False,
):
    """
    De-serialize a JSON file into a catalog.
    """
    from tilemaker import database as db

    with open(filename, "r") as f:
        data = TypeAdapter(list[CatalogIngestItem]).validate_json(f.read())

    db.create_database_and_tables()
    with db.get_session() as session:
        catalog = orm.SourceList(
            name=name, description=description, proprietary=proprietary
        )
        session.add(catalog)

        items = [
            orm.SourceItem(
                source_list=catalog,
                flux=item.flux,
                ra=item.ra,
                dec=item.dec,
                name=item.name,
                proprietary=proprietary,
            )
            for item in data
        ]
        session.add_all(items)

        session.commit()

        console.print(f"Catalog succesfully added (id: {catalog.id}).")

    return


def add_catalog(
    filename: str,
    name: str,
    description: str,
    console: Console,
    proprietary: bool = False,
):
    """
    Add a catalog to the database.
    """

    if filename.endswith(".csv"):
        _add_catalog_csv(filename, name, description, console, proprietary=proprietary)
    elif filename.endswith(".json"):
        _add_catalog_json(filename, name, description, console, proprietary=proprietary)
    else:
        console.print("Catalog must be a CSV or JSON file")

    return


def add_iqu_map(
    filename: Path,
    map_name: str,
    console: Console,
    description: str = "No description provided",
    intensity_only: bool = False,
    units: str | None = None,
    proprietary: bool = False,
    display_names: list[str] | None = None,
):
    QUANTITY_MAP = {
        "uK": "T",
        "K": "T",
        "Jy": "F",
        "mJy": "F",
    }

    BOUNDS_MAP = {
        "uK": (-500.0, 500.0),
        "K": (-5e-4, 5e-4),
        "Jy": (-20e-3, 20e-3),
        "mJy": (-20, 20),
    }

    import numpy as np

    import tilemaker.database as db
    import tilemaker.orm
    from tilemaker.processing.fits_simple import FITSFile, LayerTree

    db.create_database_and_tables()

    fits_file = FITSFile(filename=filename, log_scale_data=False)
    map_name = map_name
    description = description

    with db.get_session() as session:
        add = []

        map_metadata = (
            session.query(tilemaker.orm.Map).filter_by(name=map_name).one_or_none()
        )

        if map_metadata is None:
            map_metadata = tilemaker.orm.Map(
                name=map_name,
                description=description,
                proprietary=proprietary,
            )

            add.append(map_metadata)

            console.print("Found map:", map_metadata)
        else:
            console.print(
                f"Map {map_name} already exists in the database, adding layers"
            )

        if display_names and (
            len(display_names) != len(fits_file.individual_trees) and not intensity_only
        ):
            console.print(
                "Display names provided do not match the number of bands in the FITS file",
                len(display_names),
                len(fits_file.individual_trees),
            )
            return

        for index, fits_image in enumerate(fits_file.individual_trees):
            if intensity_only and fits_image.identifier != "I":
                continue

            quantity = f"{QUANTITY_MAP.get(units, 'T')} ({str(fits_image.identifier)})"
            frequency = f"{fits_image.header.get('FREQ', 'Unknown Frequency')}"
            display_name = display_names[index] if display_names else None
            display_name = display_name or f"{quantity} ({frequency})"

            tile_size = fits_image.tile_size
            number_of_layers = fits_image.number_of_levels

            tree = LayerTree(
                number_of_layers=number_of_layers,
                image_pixel_size=tile_size,
                image=fits_image,
            )

            top_right, bottom_left = fits_image.world_size_degrees()

            if fits_image.identifier in {"Q", "U"}:
                lower_bound, upper_bound = [
                    x * 0.1 for x in BOUNDS_MAP.get(units, [-500.0, 500.0])
                ]
            else:
                lower_bound, upper_bound = BOUNDS_MAP.get(units, [-500.0, 500.0])

            band = tilemaker.orm.Band(
                map=map_metadata,
                map_name=map_name,
                tiles_available=True,
                levels=number_of_layers,
                tile_size=tile_size,
                units=units,
                band_display_name=display_name,
                quantity=quantity,
                recommended_cmap_min=lower_bound,
                recommended_cmap_max=upper_bound,
                recommended_cmap="RdBu_r",
                bounding_left=bottom_left[0].value,
                bounding_right=top_right[0].value,
                bounding_top=top_right[1].value,
                bounding_bottom=bottom_left[1].value,
                proprietary=proprietary,
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
                proprietary=proprietary,
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
                                proprietary=proprietary,
                            )
                        )

            add += [band, histogram] + tile_metadata

            session.add_all(add)
            session.commit()

            add = []


def add_box(
    name: str,
    top_left: tuple[float, float],
    bottom_right: tuple[float, float],
    console: Console,
    description: str | None = None,
    proprietary: bool = False,
):
    """
    Add a highlight box to the database.
    """
    import tilemaker.database as db
    import tilemaker.orm

    db.create_database_and_tables()

    with db.get_session() as session:
        box = tilemaker.orm.HighlightBox(
            name=name,
            description=description,
            top_left_ra=top_left[0],
            top_left_dec=top_left[1],
            bottom_right_ra=bottom_right[0],
            bottom_right_dec=bottom_right[1],
            proprietary=proprietary,
        )

        console.print("Adding", box)

        session.add(box)
        session.commit()

    return


def add_compton_map(
    filename: Path,
    map_name: str,
    console: Console,
    description: str = "No description provided",
    proprietary: bool = False,
    display_name: str | None = None,
):
    import numpy as np

    import tilemaker.database as db
    import tilemaker.orm
    from tilemaker.processing.fits_simple import FITSFile, LayerTree

    db.create_database_and_tables()

    fits_file = FITSFile(filename=filename, log_scale_data=True)
    description = description

    with db.get_session() as session:
        add = []

        if (map_metadata := session.get(tilemaker.orm.Map, map_name)) is None:
            map_metadata = tilemaker.orm.Map(
                name=map_name, description=description, proprietary=proprietary
            )

            add.append(map_metadata)

            console.print("Found map:", map_metadata)
        else:
            console.print(f"Map {map_name} already exists in the database")
            return

        for fits_image in fits_file.individual_trees:
            tile_size = fits_image.tile_size
            number_of_layers = fits_image.number_of_levels

            tree = LayerTree(
                number_of_layers=number_of_layers,
                image_pixel_size=tile_size,
                image=fits_image,
            )

            top_right, bottom_left = fits_image.world_size_degrees()

            lower_bound, upper_bound = (-6, -4)

            band = tilemaker.orm.Band(
                map=map_metadata,
                map_name=map_name,
                tiles_available=True,
                levels=number_of_layers,
                tile_size=tile_size,
                units="log",
                band_display_name=display_name or "Compton-y",
                quantity="y",
                recommended_cmap_min=lower_bound,
                recommended_cmap_max=upper_bound,
                recommended_cmap="viridis",
                bounding_left=bottom_left[0].value,
                bounding_right=top_right[0].value,
                bounding_top=top_right[1].value,
                bounding_bottom=bottom_left[1].value,
                proprietary=proprietary,
            )

            console.print("Ingesting:", band)

            center = (lower_bound + upper_bound) / 2
            dx = (upper_bound - lower_bound) / 2

            H, edges = fits_image.histogram_raw_data(
                n_bins=128, min=center - 4 * dx, max=center + 4 * dx
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
                proprietary=proprietary,
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
                                proprietary=proprietary,
                            )
                        )

            add += [band, histogram] + tile_metadata

            session.add_all(add)
            session.commit()

            add = []
