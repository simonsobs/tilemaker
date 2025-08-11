"""
Extract a sub-map from a band.
"""

import itertools
import math

import numpy as np
from astropy.coordinates import SkyCoord, StokesCoord
from astropy.units import deg

from tilemaker.metadata.definitions import MapGroup
from tilemaker.providers.core import PullableTile, PushableTile, Tiles


def extract(
    layer_id: str,
    left: float,
    right: float,
    top: float,
    bottom: float,
    tiles: Tiles,
    metadata: list[MapGroup],
    grants: set[str],
) -> tuple[np.array, list[PushableTile]]:
    """
    Extract a sub-map from a band between RA and Dec ranges (in degrees).

    Parameters
    ----------
    layer_id : str
        The ID of the layer to extract the sub-map from.
    left : float
        The left-most RA value of the sub-map (deg).
    right : float
        The right-most RA value of the sub-map (deg).
    top : float
        The top-most Dec value of the sub-map (deg).
    bottom : float
        The bottom-most Dec value of the sub-map (deg).
    tiles: Tiles
        Tile providers
    metadata: list[MapGroup]
        Metadata object
    grants: set[str]
        Grants of the requesting user
    """

    # Use wcs to go from RA/Dec to pixel values.
    # Figure out what tiles those cover.
    # Create an appropraitely sized buffer.
    # Load the tiles and push the data into the buffer.

    # Find that there layer
    layer = next(
        (
            lyr
            for lyr in itertools.chain.from_iterable(
                band.layers
                for group in metadata
                for map in group.maps
                for band in map.bands
            )
            if lyr.layer_id == layer_id
        ),
        None,
    )

    if layer is None or (layer.grant is not None and layer.grant not in grants):
        raise ValueError(f"Layer with ID {layer_id} not found.")

    wcs = layer.provider.get_wcs()

    # Convert RA/Dec to pixel values. No idea why we need to take the negative here.
    # Probably something I don't understand about wcs.
    tr = SkyCoord(ra=-right * deg, dec=top * deg)
    bl = SkyCoord(ra=-left * deg, dec=bottom * deg)

    if layer.provider.index is not None:
        right_pix, top_pix, _ = wcs.world_to_pixel(
            tr, StokesCoord(layer.provider.index)
        )
        left_pix, bottom_pix, _ = wcs.world_to_pixel(
            bl, StokesCoord(layer.provider.index)
        )
    else:
        right_pix, top_pix = wcs.world_to_pixel(tr)
        left_pix, bottom_pix = wcs.world_to_pixel(bl)

    print(left_pix, top_pix, right_pix, bottom_pix, tr, bl)

    # Convert to integers
    left_pix = int(left_pix)
    top_pix = int(top_pix)
    right_pix = int(right_pix)
    bottom_pix = int(bottom_pix)

    buffer = np.zeros((int(top_pix - bottom_pix), (int(right_pix - left_pix))))

    # Figure out which tiles we overlap.
    end_tile_x = int(math.ceil(float(right_pix) / layer.tile_size))
    start_tile_x = int(math.floor(float(left_pix) / layer.tile_size))
    end_tile_y = int(math.ceil(top_pix / layer.tile_size))
    start_tile_y = int(math.floor(bottom_pix / layer.tile_size))

    # Load the tiles and push the data into the buffer.
    pushables = []

    for x in range(start_tile_x, end_tile_x + 1):
        for y in range(start_tile_y, end_tile_y + 1):
            tile, this_push = tiles.pull(
                PullableTile(
                    layer_id=layer_id,
                    x=x,
                    y=y,
                    level=layer.number_of_levels - 1,
                    grants=grants,
                )
            )

            pushables.extend(this_push)

            if tile is None or tile.data is None:
                continue

            tile_data = tile.data

            # First thing to do is to figure out which part of the tile overlaps with our buffer.
            start_x = max(0, min(layer.tile_size, left_pix - x * layer.tile_size))
            end_x = min(layer.tile_size, max(0, right_pix - x * layer.tile_size))
            dx = end_x - start_x

            start_y = max(0, min(layer.tile_size, bottom_pix - y * layer.tile_size))
            end_y = min(layer.tile_size, max(0, top_pix - y * layer.tile_size))
            dy = end_y - start_y

            tile_selector = np.s_[start_y:end_y, start_x:end_x]

            # Now for buffer
            start_x = max(min(x * layer.tile_size - left_pix, right_pix), 0)
            end_x = min(right_pix, max(0, start_x + dx))

            start_y = max(min(y * layer.tile_size - bottom_pix, top_pix), 0)
            end_y = min(top_pix, max(0, start_y + dy))

            buffer_selector = np.s_[start_y:end_y, start_x:end_x]

            buffer[buffer_selector] = tile_data[tile_selector]

    return buffer, pushables
