"""
Extract a sub-map from a band.
"""

import math

import numpy as np

from tilemaker import orm


def extract(
    band_id: int,
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> np.array:
    """
    Extract a sub-map from a band between RA and Dec ranges (in degrees).

    Parameters
    ----------
    band_id : int
        The ID of the band to extract the sub-map from.
    left : float
        The left-most RA value of the sub-map (deg).
    right : float
        The right-most RA value of the sub-map (deg).
    top : float
        The top-most Dec value of the sub-map (deg).
    bottom : float
        The bottom-most Dec value of the sub-map (deg).
    """

    from tilemaker.database import get_session

    # Use wcs to go from RA/Dec to pixel values.
    # Figure out what tiles those cover.
    # Create an appropraitely sized buffer.
    # Load the tiles and push the data into the buffer.

    with get_session() as session:
        band = session.get(orm.Band, band_id)

        if band is None:
            raise ValueError(f"Band with ID {band_id} not found.")

        wcs = band.wcs

        # Convert RA/Dec to pixel values. No idea why we need to take the negative here.
        # Probably something I don't understand about wcs.
        right_pix, top_pix = wcs.world_to_pixel_values(-right, top)
        left_pix, bottom_pix = wcs.world_to_pixel_values(-left, bottom)

        # Convert to integers
        left_pix = int(left_pix)
        top_pix = int(top_pix)
        right_pix = int(right_pix)
        bottom_pix = int(bottom_pix)

        buffer = np.zeros((int(top_pix - bottom_pix), (int(right_pix - left_pix))))

        # Figure out which tiles we overlap.
        end_tile_x = int(math.ceil(float(right_pix) / band.tile_size))
        start_tile_x = int(math.floor(float(left_pix) / band.tile_size))
        end_tile_y = int(math.ceil(top_pix / band.tile_size))
        start_tile_y = int(math.floor(bottom_pix / band.tile_size))

        # Load the tiles and push the data into the buffer.
        for x in range(start_tile_x, end_tile_x + 1):
            for y in range(start_tile_y, end_tile_y + 1):
                tile = session.get(orm.Tile, (band.levels - 1, x, y, band_id))

                if tile is None or tile.data is None:
                    continue

                tile_data = np.frombuffer(tile.data, dtype=tile.data_type).reshape(
                    (band.tile_size, band.tile_size)
                )

                # First thing to do is to figure out which part of the tile overlaps with our buffer.
                start_x = max(0, min(band.tile_size, left_pix - x * band.tile_size))
                end_x = min(band.tile_size, max(0, right_pix - x * band.tile_size))
                dx = end_x - start_x

                start_y = max(0, min(band.tile_size, bottom_pix - y * band.tile_size))
                end_y = min(band.tile_size, max(0, top_pix - y * band.tile_size))
                dy = end_y - start_y

                tile_selector = np.s_[start_y:end_y, start_x:end_x]

                # Now for buffer
                start_x = max(min(x * band.tile_size - left_pix, right_pix), 0)
                end_x = min(right_pix, max(0, start_x + dx))

                start_y = max(min(y * band.tile_size - bottom_pix, top_pix), 0)
                end_y = min(top_pix, max(0, start_y + dy))

                buffer_selector = np.s_[start_y:end_y, start_x:end_x]

                buffer[buffer_selector] = tile_data[tile_selector]

    return buffer
