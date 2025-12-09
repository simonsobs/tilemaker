"""
Extract a sub-map from a band.
"""

import math
from time import perf_counter

import numpy as np
import structlog
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

from tilemaker.metadata.core import DataConfiguration
from tilemaker.providers.core import PullableTile, PushableTile, Tiles


def extract(
    layer_id: str,
    left: float,
    right: float,
    top: float,
    bottom: float,
    tiles: Tiles,
    metadata: DataConfiguration,
    grants: set[str],
    show_grid: bool = False,
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
    metadata: DataConfiguration
        Metadata object
    grants: set[str]
        Grants of the requesting user
    show_grid: bool = False
        Whether to 'show' the grid (grids are set as NaN values)
    """

    log = structlog.get_logger()

    # Use wcs to go from RA/Dec to pixel values.
    # Figure out what tiles those cover.
    # Create an appropraitely sized buffer.
    # Load the tiles and push the data into the buffer.

    # Find that there layer
    layer = next(
        (lyr for lyr in metadata.layers if lyr.layer_id == layer_id),
        None,
    )

    log = log.bind(layer_id=layer_id, grants=grants)

    if layer is None or (layer.grant is not None and layer.grant not in grants):
        log.warning("extractor.no_layer")
        raise ValueError(f"Layer with ID {layer_id} not found.")

    # This is the base WCS, aligned with the _grid of the file_
    # not the _tile grid_, which is what we want.
    base_wcs = layer.provider.get_wcs()

    CDELT_RA = base_wcs.wcs.cdelt[0]
    CDELT_DEC = base_wcs.wcs.cdelt[1]

    NAXIS1 = int(360.0 / abs(CDELT_RA))
    NAXIS2 = int(180.0 / abs(CDELT_DEC))

    # The tile grid behaves like a giant image with the same
    # resolution as the base layer, but covering the whole sky.
    wcs = WCS(
        {
            "NAXIS": 2,
            "CRPIX1": NAXIS1 * 0.5,
            "CRPIX2": NAXIS2 * 0.5 + 0.5,
            "CRVAL1": 0.0,
            "NAXIS1": NAXIS1,
            "NAXIS2": NAXIS2,
            "CRVAL2": 0.0,
            "CDELT1": CDELT_RA,
            "CDELT2": -CDELT_DEC,
            "CTYPE1": "RA---CAR",
            "CTYPE2": "DEC--CAR",
            "CUNIT1": "deg",
            "CUNIT2": "deg",
            "LONPOLE": 90.0,
            "LATPOLE": 0.0,
            "RADESYS": "ICRS",
        }
    )

    # Convert RA/Dec to pixel values. No idea why we need to take the negative here.
    # Probably something I don't understand about wcs.
    tr = SkyCoord(ra=right, dec=top, unit="deg")
    bl = SkyCoord(ra=left, dec=bottom, unit="deg")

    log = log.bind(tr=tr, bl=bl)

    right_pix, top_pix = wcs.world_to_pixel(tr)
    left_pix, bottom_pix = wcs.world_to_pixel(bl)

    # Convert to integers
    left_pix = int(left_pix)
    top_pix = int(top_pix)
    right_pix = int(right_pix)
    bottom_pix = int(bottom_pix)

    if left_pix > right_pix:
        left_pix, right_pix = right_pix, left_pix
    if bottom_pix > top_pix:
        bottom_pix, top_pix = top_pix, bottom_pix

    y_size = top_pix - bottom_pix
    x_size = right_pix - left_pix

    log = log.bind(size=(y_size, x_size))

    buffer = np.zeros((int(y_size), (int(x_size))))

    # Figure out which tiles we overlap.
    end_tile_x = int(math.ceil(float(right_pix) / layer.tile_size))
    start_tile_x = int(math.floor(float(left_pix) / layer.tile_size))
    end_tile_y = int(math.ceil(top_pix / layer.tile_size))
    start_tile_y = int(math.floor(bottom_pix / layer.tile_size))

    # Load the tiles and push the data into the buffer.
    pushables = []
    start_time = perf_counter()
    n_found = 0
    n_missed = 0

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
                n_missed += 1
                continue

            n_found += 1
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
            start_x = max(min(x * layer.tile_size - left_pix, x_size - 1), 0)
            end_x = min(x_size, max(0, start_x + dx))

            start_y = max(min(y * layer.tile_size - bottom_pix, y_size - 1), 0)
            end_y = min(y_size, max(0, start_y + dy))

            buffer_selector = np.s_[start_y:end_y, start_x:end_x]

            buffer[buffer_selector] = tile_data[tile_selector]

            # Highlight edges
            if show_grid:
                buffer[end_y - 1, start_x : end_x - 1] = np.nan
                buffer[start_y, start_x : end_x - 1] = np.nan
                buffer[start_y : end_y - 1, start_x] = np.nan
                buffer[start_y : end_y - 1, end_x - 1] = np.nan

    end_time = perf_counter()
    log = log.bind(dt=end_time - start_time, n_found=n_found, n_missed=n_missed)

    log = log.info("extractor.complete")

    return buffer, pushables
