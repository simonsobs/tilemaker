"""
Command-line script for ingesting FITS files into the database.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, CliApp, CliImplicitFlag

QUANTITY_MAP = {
    "uK": "T",
}

cmap_min_dict  = {
    "I" : -500.0,
    "Q" : -20.0,
    "U" : -20.0,
    "kappa" : -0.1,
    "compton_y": -1e-5, ##need to check what cmap range is best
    "mask": 0
}

cmap_max_dict  = {
    "I" : 500.0,
    "Q" : 20.0,
    "U" : 20.0,
    "kappa" : 0.1,
    "compton_y": 1e-5, ##need to check what cmap range is best
    "mask": 1.
}

hist_min_dict = {
    "I" : -2000.0,
    "Q" : -80.0,
    "U" : -80.0,
    "kappa": -0.4,
    "compton_y" : -4e-5,
    "mask" : 0.,
}

hist_max_dict = {
    "I": 2000.0,
    "Q": 80.0,
    "U": 80.0,
    "kappa" : 0.4,
    "compton_y" : 4e-5,
    "mask" : 1.,
}

class FitsIngestSettings(BaseSettings):
    """
    Ingest FITS files into the tilemaker database for serving to clients.
    Important note: this script only uses the first HDU in the FITS file, and assumes
    that it conforms to the ACT/SO data format.
    """

    filename: Path
    "The FITS file to ingest into the database"
    map_name: str
    "The name of the map to create in the database"
    description: str = "No description provided."
    "A description of the map"
    #intensity_only: CliImplicitFlag[bool] = False
    #"Only ingest the intensity data from the FITS file, not polarization"
    map_type: str | None = None
    "Type of map. Either cmb, kappa, compton_y map or mask."
    telescope: str | None = None
    "The telescope that was used to create this map; if not provided we read it from the map"
    data_release: str | None = None
    "The data release that this map is part of; if not provided we read it from the map"
    season: str | None = None
    "The season that this map was taken in; if not provided we read it from the map"
    tags: str | None = None
    "Any tags that are associated with this map; if not provided we read it from the map"
    patch: str | None = None
    "The patch of the sky that this map covers; if not provided we read it from the map"
    frequency: str | None = None
    "The frequency of the map; if not provided we read it from the map"

    def cli_cmd(self) -> None:
        ingest_map(self)


def ingest_map(settings: "FitsIngestSettings"):
    import numpy as np

    import tilemaker.database as db
    import tilemaker.orm
    from tilemaker.processing.fits_simple import FITSFile, LayerTree

    db.create_database_and_tables()

    fits_file = FITSFile(filename=settings.filename, map_type=settings.map_type)
    map_name = settings.map_name
    description = settings.description
    map_type = settings.map_type

    with db.get_session() as session:
        add = []

        if (map_metadata := session.get(tilemaker.orm.Map, map_name)) is None:
            telescope = (
                settings.telescope
                if settings.telescope is not None
                else fits_file.individual_trees[0].header.get("TELESCOP", None)
            )
            data_release = (
                settings.data_release
                if settings.data_release is not None
                else fits_file.individual_trees[0].header.get("RELEASE", None)
            )
            season = (
                settings.season
                if settings.season is not None
                else fits_file.individual_trees[0].header.get("SEASON", None)
            )
            tags = (
                settings.tags
                if settings.tags is not None
                else fits_file.individual_trees[0].header.get("ACTTAGS", None)
            )
            patch = (
                settings.patch
                if settings.patch is not None
                else fits_file.individual_trees[0].header.get("PATCH", None)
            )

            map_metadata = tilemaker.orm.Map(
                name=map_name,
                description=description,
                map_type=map_type,
                telescope=telescope,
                data_release=data_release,
                season=season,
                tags=tags,
                patch=patch,
            )

            add.append(map_metadata)

            print("Found map:", map_metadata)
        else:
            print(f"Map {map_name} already exists in the database")
            exit(1)

        for fits_image in fits_file.individual_trees:
            #if settings.intensity_only and fits_image.identifier != "I": ##disabling this since we do not have the intensity_only flag
            #    continue

            tile_size = fits_image.tile_size
            number_of_layers = fits_image.number_of_levels

            tree = LayerTree(
                number_of_layers=number_of_layers,
                image_pixel_size=tile_size,
                image=fits_image,
            )

            top_right, bottom_left = fits_image.world_size_degrees()

            frequency = (
                settings.frequency
                if settings.frequency is not None
                else fits_image.header.get("FREQ", "f000").replace("f", "")
            )
            
            rec_cmap_min = cmap_min_dict[fits_image.identifier]
            rec_cmap_max = cmap_max_dict[fits_image.identifier]
            
            band = tilemaker.orm.Band(
                map=map_metadata,
                tiles_available=True,
                levels=number_of_layers,
                tile_size=tile_size,
                frequency=frequency,
                map_type=str(fits_image.identifier),
                units=str(fits_image.header.get("BUNIT", "")),
                recommended_cmap_min=rec_cmap_min,  ##changed hardcoded value
                recommended_cmap_max=rec_cmap_max, ##changed hardcoded value
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

            hist_min = hist_min_dict[fits_image.identifier]
            hist_max = hist_max_dict[fits_image.identifier]
            n_bins = 128 
            
            ## do we need diff n_bins depending on map_type?? don't know!!
            H, edges = fits_image.histogram_raw_data(
                n_bins=n_bins, min=hist_min, max=hist_max
            )

            histogram = tilemaker.orm.Histogram(
                band=band,
                start=hist_min,
                end=hist_max,
                bins=n_bins,
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


def main():
    CliApp.run(FitsIngestSettings)
