"""
Tile providers that read directly from FITS files.
"""

from itertools import chain
from time import perf_counter

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.io.fits import ImageHDU
from astropy.nddata import Cutout2D, NoOverlapError
from astropy.wcs import WCS
from structlog.types import FilteringBoundLogger

from tilemaker.metadata.definitions import FITSLayerProvider, Layer, MapGroup

from .core import PullableTile, PushableTile, TileNotFoundError, TileProvider


def extract_patch_from_fits(
    hdu: ImageHDU,
    ra_range: tuple[float, float],
    dec_range: tuple[float, float],
    subsample_every: int,
    log: FilteringBoundLogger,
    index: int | None = None,
) -> np.ndarray | None:
    """
    Extract an individual patch from a FITS file. Requires that you have already opened
    the file and have extracted a HDU.
    """
    wcs = WCS(hdu.header)

    if index is not None:
        wcs = wcs.dropaxis(-1)

    # First find midpoint of ra range and apply units. We know it's square. Also find 'radius'.
    ra_left, ra_right = [x * u.deg for x in ra_range]
    dec_left, dec_right = [x * u.deg for x in dec_range]

    ra_center = 0.5 * (ra_left + ra_right)
    dec_center = 0.5 * (dec_left + dec_right)

    radius = ra_right - ra_left

    log = log.bind(ra_center=ra_center, dec_center=dec_center, radius=radius)

    if index is not None:
        pre_sel = np.s_[index, :, :]
    else:
        pre_sel = np.s_

    start = perf_counter()
    try:
        cutout = Cutout2D(
            hdu.data[pre_sel],
            position=SkyCoord(ra_center, dec_center),
            size=radius,
            wcs=wcs,
            mode="partial",
        )
    except NoOverlapError:
        end = perf_counter()
        log = log.bind(dt=end - start)
        log.debug("fits.no_data")
        return None

    if subsample_every > 1:
        log = log.bind(subsample_every=subsample_every)
        cutout = cutout.data[::subsample_every, ::subsample_every]
    else:
        cutout = cutout.data

    end = perf_counter()
    log.debug("fits.pulled", dt=end - start)

    return cutout


class FITSTileProvider(TileProvider):
    layers: dict[int, Layer]
    subsample: bool

    def __init__(
        self,
        map_groups: list[MapGroup],
        subsample: bool = True,
        internal_provider_id: str | None = None,
    ):
        self.layers = {
            x.layer_id: x
            for x in filter(
                lambda x: isinstance(x.provider, FITSLayerProvider),
                chain.from_iterable(
                    band.layers
                    for map_group in map_groups
                    for map in map_group.maps
                    for band in map.bands
                ),
            )
        }
        self.subsample = subsample
        super().__init__(internal_provider_id=internal_provider_id)

    def _get_tile_info(self, tile: PullableTile):
        RA_OFFSET = 0.0
        RA_RANGE = 2.0 * 180.0
        DEC_OFFSET = -0.5 * 180.0
        DEC_RANGE = 180.0

        ra_per_tile = RA_RANGE / 2 ** (tile.level + 1)
        dec_per_tile = DEC_RANGE / 2 ** (tile.level)

        def pix(v, w):
            return ((ra_per_tile * v + RA_OFFSET), (dec_per_tile * w + DEC_OFFSET))

        # Our map viewer operates in the -180 -> 180 space. However, the underlying
        # astropy wcs lives in 360 -> 0 RA space. All operations internally in this
        # code are done in astropy's co-ordinate system. So we need to flip/fold our
        # input x to be reconfigrued to the astropy space.
        x = tile.x
        if tile.level != 0:
            # tile.level of zero requires no flipping apart from at the tile tile.level.
            midpoint = 2 ** (tile.level)
            if x < midpoint:
                x = (2 ** (tile.level) - 1) - x
            else:
                x = (2 ** (tile.level) - 1) - (x - midpoint) + midpoint

        bottom_left = pix(x, tile.y)
        top_right = pix(x + 1, tile.y + 1)

        return {
            "ra_range": [bottom_left[0], top_right[0]],
            "dec_range": [bottom_left[1], top_right[1]],
        }

    def pull(self, tile: PullableTile):
        log = self.logger.bind(tile_hash=tile.hash)

        layer = self.layers.get(tile.layer_id, None)

        if not layer:
            log.debug("fits.layer_not_found")
            raise TileNotFoundError(f"Band {tile.layer_id} not available")

        level_difference = layer.number_of_levels - tile.level - 1

        if not self.subsample and level_difference:
            log.debug("fits.not_subsampled")
            raise TileNotFoundError("Not bottom level")

        subsample_every = 2 ** (level_difference)

        with fits.open(layer.provider.filename) as h:
            hdu = h[layer.provider.hdu]

            patch = extract_patch_from_fits(
                hdu=hdu,
                **self._get_tile_info(tile=tile),
                index=layer.provider.index,
                subsample_every=subsample_every,
                log=log,
            )

        return PushableTile(
            layer_id=tile.layer_id,
            x=tile.x,
            y=tile.y,
            level=tile.level,
            grant=layer.grant,
            data=patch,
            source=self.internal_provider_id,
        )

    def push(self, tile: PushableTile):
        return
