"""
Command-line script for ingesting FITS files into the database.
"""

import argparse as ap
from pathlib import Path

QUANTITY_MAP = {
    "uK": "T",
}

parser = ap.ArgumentParser(
    description=(
        "Ingest FITS files into the tilemaker database for serving to clients. "
        "Important note: this script only uses the first HDU in the FITS file, and assumes "
        "that it conforms to the ACT/SO data format."
    )
)

parser.add_argument(
    "filename",
    type=Path,
    help="The FITS file to ingest into the database.",
)

parser.add_argument(
    "map_name",
    type=str,
    help="The name of the map to create in the database.",
)

parser.add_argument(
    "--description",
    type=str,
    default="No description provided.",
    help="A description of the map.",
)


def main():
    import numpy as np

    import tilemaker.database as db
    import tilemaker.orm
    from tilemaker.processing.fits_simple import FITSFile, LayerTree

    args = parser.parse_args()

    db.create_database_and_tables()

    fits_file = FITSFile(filename=args.filename)
    map_name = args.map_name
    description = args.description

    with db.get_session() as session:
        add = []

        if (map_metadata := session.get(tilemaker.orm.Map, map_name)) is None:
            map_metadata = tilemaker.orm.Map(
                name=map_name,
                description=description,
                telescope=fits_file.individual_trees[0].header.get("TELESCOP", None),
                data_release=fits_file.individual_trees[0].header.get("RELEASE", None),
                season=fits_file.individual_trees[0].header.get("SEASON", None),
                tags=fits_file.individual_trees[0].header.get("ACTTAGS", None),
                patch=fits_file.individual_trees[0].header.get("PATCH", None),
            )

            add.append(map_metadata)

            print("Found map:", map_metadata)
        else:
            print(f"Map {map_name} already exists in the database")
            exit(1)

        for fits_image in fits_file.individual_trees:
            tile_size = fits_image.tile_size
            number_of_layers = fits_image.number_of_levels

            tree = LayerTree(
                number_of_layers=number_of_layers,
                image_pixel_size=tile_size,
                image=fits_image,
            )

            top_right, bottom_left = fits_image.world_size_degrees()

            band = tilemaker.orm.Band(
                map=map_metadata,
                tiles_available=True,
                levels=number_of_layers,
                tile_size=tile_size,
                frequency=str(fits_image.header.get("FREQ", "").replace("f", "")),
                stokes_parameter=str(fits_image.identifier),
                units=str(fits_image.header.get("BUNIT", "")),
                recommended_cmap_min=-500.0,
                recommended_cmap_max=500.0,
                recommended_cmap="RdBu_r",
                bounding_left=bottom_left[0].value,
                bounding_right=top_right[0].value,
                bounding_top=top_right[1].value,
                bounding_bottom=bottom_left[1].value,
                quantity=QUANTITY_MAP.get(
                    str(fits_image.header.get("BUNIT", "")), None
                ),
            )

            print("Ingesting:", band)

            H, edges = fits_image.histogram_raw_data(
                n_bins=128, min=-2000.0, max=2000.0
            )

            histogram = tilemaker.orm.Histogram(
                band=band,
                start=-2000.0,
                end=2000.0,
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
                            bytes = tile_data.data.tobytes(order="C", fill_value=np.NaN)
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
