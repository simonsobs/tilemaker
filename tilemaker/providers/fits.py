"""
Tile providers that read directly from FITS files.
"""

from pathlib import Path

import numpy as np
from pydantic import BaseModel
from .core import TileNotFoundError, TileProvider, PullableTile, PushableTile
import structlog
from structlog.types import FilteringBoundLogger
from astropy.io import fits
from astropy import units
from astropy.nddata import Cutout2D, NoOverlapError
from astropy.wcs import WCS
from time import perf_counter
import math

import numpy as np
from astropy.wcs import WCS
from astropy.io.fits import ImageHDU
from astropy.coordinates import SkyCoord
import astropy.units as u


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
        log = log.bind(dt=end-start)
        log.debug("fits.no_data")
        return None

    if subsample_every > 1:
        log = log.bind(subsample_every=subsample_every)
        cutout = cutout.data[::subsample_every, ::subsample_every]
    else:
        cutout = cutout.data
    
    end = perf_counter()
    log.debug("fits.pulled", dt=end-start)

    return cutout


def calculate_tile_size(file: Path, index: int | None, hdu: int = 0) -> tuple[int, int]:
    # Need to figure out how big the whole 'map' is, i.e. moving it up
    # so that it fills the whole space.
    with fits.open(file) as h:
        wcs = WCS(h[hdu].header)

    scale = wcs.proj_plane_pixel_scales()
    scale_x_deg = scale[0]
    scale_y_deg = scale[1]

    # The full sky spans 360 deg in RA, 180 deg in Dec
    map_size_x = int(np.floor(360 * units.deg / scale_x_deg))
    map_size_y = int(np.floor(180 * units.deg / scale_y_deg))

    max_size = max(map_size_x, map_size_y)

    # See if 256 fits.
    if (map_size_x % 256 == 0) and (map_size_y % 256 == 0):
        tile_size = 256
        number_of_levels = int(math.log2(max_size // 256))
        return tile_size, number_of_levels

    # Oh no, remove all the powers of two until
    # we get an odd number.
    this_tile_size = map_size_y

    # Also don't make it too small.
    while this_tile_size % 2 == 0 and this_tile_size > 512:
        this_tile_size = this_tile_size // 2

    number_of_levels = int(math.log2(max_size // this_tile_size))
    tile_size = this_tile_size

    return tile_size, number_of_levels


class BandInfo(BaseModel):
    band_id: int
    grant: str | None

    file: Path
    hdu: int
    tile_size: int
    number_of_levels: int
    index: int | None

    @classmethod
    def from_fits(
        cls,
        file: Path,
        band_id: int,
        index: int | None,
        hdu: int = 0,
        grant: str | None = None,
    ):
        """
        Generate the required BandInfo from the file.
        """
        tile_size, number_of_levels = calculate_tile_size(
            file=file, index=index, hdu=hdu
        )

        return cls(
            band_id=band_id,
            grant=grant,
            file=file,
            hdu=hdu,
            tile_size=tile_size,
            number_of_levels=number_of_levels,
            index=index,
        )


class FITSTileProvider(TileProvider):
    bands: dict[int, BandInfo]
    subsample: bool

    def __init__(self, bands: list[BandInfo], subsample: bool = True, internal_provider_id: str | None = None):
        self.bands = {x.band_id: x for x in bands}
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

        band = self.bands.get(tile.band_id, None)

        if not band:
            log.debug("fits.band_not_found")
            raise TileNotFoundError(f"Band {tile.band_id} not available")

        level_difference = band.number_of_levels - tile.level - 1

        if not self.subsample and level_difference:
            log.debug("fits.not_subsampled")
            raise TileNotFoundError("Not bottom level")

        subsample_every = 2 ** (level_difference)

        with fits.open(band.file) as h:
            hdu = h[band.hdu]

            patch = extract_patch_from_fits(
                hdu=hdu,
                **self._get_tile_info(tile=tile),
                index=band.index,
                subsample_every=subsample_every,
                log=log
            )

        return PushableTile(
            band_id=tile.band_id,
            x=tile.x,
            y=tile.y,
            level=tile.level,
            grant=band.grant,
            data=patch,
            source=self.internal_provider_id
        )

    def push(self, tile: PushableTile):
        return
