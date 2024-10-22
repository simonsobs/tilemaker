"""
An example of building the database for a simple array.

Two modes: create database, and visualize database.
"""

import sys

import numpy as np
from sqlmodel import select

import tilemaker.database as db
import tilemaker.orm
from tilemaker.processing.simple import SimpleMapMaker

mode = sys.argv[1]

if mode == "create":
    db.create_database_and_tables()

    # Create a simple array
    array = np.empty((1024 * 2, 512 * 2), order="C")
    x, y = np.meshgrid(np.arange(512 * 2), np.arange(1024 * 2))
    array[:] = x**2 + y**2

    map_maker = SimpleMapMaker(raw_array=array)
    tiles = map_maker.make_tiles()

    with db.get_session() as session:
        map_metadata = tilemaker.orm.Map(name="Test_Map", description="A example map.")

        band = tilemaker.orm.Band(
            map=map_metadata,
            tiles_available=True,
            levels=max(tiles.keys()),
            tile_size=map_maker.tile_size,
        )

        tile_metadata = []

        for depth, tile_collection in tiles.items():
            for tile_name, tile_data in tile_collection.items():
                x, y = (int(x) for x in tile_name.split("_"))
                tile_metadata.append(
                    tilemaker.orm.Tile(
                        level=depth,
                        x=x,
                        y=y,
                        band=band,
                        data=tile_data.tobytes("C"),
                    )
                )

        session.add_all([map_metadata, band] + tile_metadata)
        session.commit()

    print("Database successfully created.")
elif mode == "delete":
    # Check that we can delete our map easily.
    with db.get_session() as session:
        session.delete(session.exec(select(tilemaker.orm.Map)).one())
        session.commit()

    print("Database successfully deleted.")
else:
    # Visualize the database.
    import matplotlib.pyplot as plt

    # Metadata
    with db.get_session() as session:
        map_metadata = session.query(tilemaker.orm.Map).first()
        band = map_metadata.bands[0]

        # Create a figure with a sub-plot for each level.
        fig, axs = plt.subplots(1, band.levels + 1, figsize=(20, 10))

        for level in range(band.levels + 1):
            tiles = (
                session.query(tilemaker.orm.Tile)
                .filter(
                    tilemaker.orm.Tile.level == level,
                    tilemaker.orm.Tile.band_id == band.id,
                )
                .all()
            )

            # Create a 2D array to hold the tiles. We know the size of
            # this array also from the metadata.
            n_tiles_x = 2 ** (level + 1)
            n_tiles_y = 2 ** (level)

            tile_array = np.empty(
                (n_tiles_x * band.tile_size, n_tiles_y * band.tile_size), order="C"
            )

            for tile in tiles:
                x_range = np.s_[tile.x * band.tile_size : (tile.x + 1) * band.tile_size]
                y_range = np.s_[tile.y * band.tile_size : (tile.y + 1) * band.tile_size]
                x = tile.x
                y = tile.y
                tile_data = np.frombuffer(tile.data, dtype=np.float64).reshape(
                    band.tile_size, band.tile_size
                )
                tile_array[x_range, y_range] = tile_data

            axs[level].imshow(tile_array, cmap="viridis")
            axs[level].set_title(f"Level {level}")

        plt.show()
