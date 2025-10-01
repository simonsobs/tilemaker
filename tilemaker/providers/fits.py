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
from astropy.nddata import NoOverlapError
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales, skycoord_to_pixel
from structlog.types import FilteringBoundLogger

from tilemaker.metadata.definitions import FITSLayerProvider, Layer, MapGroup

from .core import PullableTile, PushableTile, TileNotFoundError, TileProvider


def overlap_slices(
    large_array_shape,
    small_array_shape,
    position,
    slice_step,
):
    """
    Extended from nddata.utils
    """
    limit_rounding_method = np.floor

    if np.isscalar(small_array_shape):
        small_array_shape = (small_array_shape,)
    if np.isscalar(large_array_shape):
        large_array_shape = (large_array_shape,)
    if np.isscalar(position):
        position = (position,)

    if any(~np.isfinite(position)):
        raise ValueError("Input position contains invalid values (NaNs or infs).")

    if len(small_array_shape) != len(large_array_shape):
        raise ValueError(
            '"large_array_shape" and "small_array_shape" must '
            "have the same number of dimensions."
        )

    if len(small_array_shape) != len(position):
        raise ValueError(
            '"position" must have the same number of dimensions as "small_array_shape".'
        )

    # define the min/max pixel indices
    # round according to the limit_rounding_method
    try:
        indices_min = [
            int(limit_rounding_method((pos - (small_shape / 2.0)) / slice_step))
            for (pos, small_shape) in zip(position, small_array_shape)
        ]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Limit rounding method must accept a single number as input and return a single number."
        ) from exc
    indices_max = [
        int(idx_min + small_shape / slice_step)
        for (idx_min, small_shape) in zip(indices_min, small_array_shape)
    ]

    for e_max in indices_max:
        if e_max < 0 or (e_max == 0 and small_array_shape != (0, 0)):
            raise NoOverlapError("Arrays do not overlap.")
    for e_min, large_shape in zip(indices_min, large_array_shape):
        if e_min >= large_shape:
            raise NoOverlapError("Arrays do not overlap.")

    # Set up slices
    slices_large = tuple(
        slice(
            max(0, indices_min * slice_step),
            min((large_shape // slice_step), indices_max) * slice_step,
            slice_step,
        )
        for (indices_min, indices_max, large_shape) in zip(
            indices_min, indices_max, large_array_shape
        )
    )

    slices_small = tuple(
        slice(
            max(0, -indices_min),
            min(large_shape // slice_step - indices_min, indices_max - indices_min),
        )
        for (indices_min, indices_max, large_shape) in zip(
            indices_min, indices_max, large_array_shape
        )
    )

    return slices_large, slices_small


def extract_array(
    array_large,
    shape,
    position,
    slice_step,
    fill_value=None,
):
    """
    Simplified from nddata.utils from astropy. Fixed to 'partial' mode
    """

    # Default fill_value
    if fill_value is None:
        if np.issubdtype(array_large.dtype, np.floating):
            fill_value = np.nan
        elif np.issubdtype(array_large.dtype, np.integer):
            fill_value = 0
        elif np.issubdtype(array_large.dtype, np.bool_):
            fill_value = False
        
    if np.isscalar(shape):
        shape = (shape,)
    if np.isscalar(position):
        position = (position,)

    large_slices, small_slices = overlap_slices(
        array_large.shape, shape, position, slice_step=slice_step
    )

    # For tileviewer, this is _not_ a rare case!

    extracted_array = np.zeros(
        [x // slice_step for x in shape], dtype=array_large.dtype
    )
    try:
        extracted_array[:] = fill_value
    except ValueError as exc:
        exc.args += (
            "fill_value is inconsistent with the data type of "
            "the input array (e.g., fill_value cannot be set to "
            "np.nan if the input array has integer type). Please "
            "change either the input array dtype or the "
            "fill_value.",
        )
        raise exc

    try:
        extracted_array[small_slices] = array_large[large_slices]
    except ValueError:
        raise NoOverlapError("Unknown no overlap error.")

    return extracted_array


def extract_shape_for_cutout(
    position: SkyCoord, size: u.Quantity, wcs: WCS
) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Extracted from Cutout2D code.
    """
    position = skycoord_to_pixel(position, wcs, mode="all")

    size = np.atleast_1d(size)
    if len(size) == 1:
        size = np.repeat(size, 2)

    shape = np.zeros(2).astype(int)
    pixel_scales = None
    # ``size`` can have a mixture of int and Quantity (and even units),
    # so evaluate each axis separately
    for axis, side in enumerate(size):
        if side.unit == u.pixel:
            shape[axis] = int(np.round(side.value))
        elif side.unit.physical_type == "angle":
            if pixel_scales is None:
                pixel_scales = u.Quantity(
                    proj_plane_pixel_scales(wcs), wcs.wcs.cunit[axis]
                )
            shape[axis] = int(np.round((side / pixel_scales[axis]).decompose()))
        else:
            raise ValueError(
                "shape can contain Quantities with only pixel or angular units"
            )

    # reverse position because extract_array and overlap_slices
    # use (y, x), but keep the input position
    pos_yx = position[::-1]

    return tuple(pos_yx), tuple(shape)


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

    # Correct the haeder if we need to; some headers have goemetries that
    # require double wrapping the sphere -- not compatible with astropy.
    if abs(hdu.header["CRPIX1"]) > hdu.header["NAXIS1"]:
        # Reset the CRPIX1 to as close to zero as possible.
        crval_original = hdu.header["CRVAL1"]
        delt = hdu.header["CDELT1"]

        # Leave any partial pixels unchanged
        pixel_change = float(int(hdu.header["CRPIX1"]))
        new_crpix = hdu.header["CRPIX1"] - pixel_change
        new_crval = crval_original - pixel_change * delt

        hdu.header["CRPIX1"] = new_crpix
        hdu.header["CRVAL1"] = new_crval

    wcs = WCS(hdu.header)

    if index is not None:
        wcs = wcs.dropaxis(-1)

    # First find midpoint of ra range and apply units. We know it's square. Also find 'radius'.
    ra_left, ra_right = [x * u.deg for x in ra_range]
    dec_left, dec_right = [x * u.deg for x in dec_range]

    ra_center = 0.5 * (ra_left + ra_right)
    dec_center = 0.5 * (dec_left + dec_right)

    radius = abs(ra_right - ra_left)

    log = log.bind(ra_center=ra_center, dec_center=dec_center, radius=radius)

    if index is not None:
        use_data = hdu.data[index]
    else:
        use_data = hdu.data

    start = perf_counter()
    try:
        pos_yx, shape = extract_shape_for_cutout(
            position=SkyCoord(ra=ra_center, dec=dec_center), size=radius, wcs=wcs
        )
        log = log.bind(pos_yx=pos_yx, shape=shape)
        cutout = extract_array(use_data, shape, pos_yx, slice_step=subsample_every)
    except NoOverlapError:
        pixel_scales = radius / u.Quantity(
            proj_plane_pixel_scales(wcs), wcs.wcs.cunit[0]
        )
        log = log.bind(
            pixel=skycoord_to_pixel(SkyCoord(ra=ra_center, dec=dec_center), wcs=wcs),
            pixel_scales=pixel_scales,
        )

        end = perf_counter()
        log = log.bind(dt=end - start)
        log.debug("fits.no_data")

        return None

    if subsample_every > 1:
        log = log.bind(subsample_every=subsample_every)
        # cutout = cutout[::subsample_every, ::subsample_every]
    else:
        cutout = cutout

    end = perf_counter()
    log.debug("fits.pulled", dt=end - start)

    return np.fliplr(cutout)


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
        RA_OFFSET = -180.0
        RA_RANGE = 2.0 * 180.0
        DEC_OFFSET = -0.5 * 180.0
        DEC_RANGE = 180.0

        ra_per_tile = RA_RANGE / 2 ** (tile.level + 1)
        dec_per_tile = DEC_RANGE / 2 ** (tile.level)

        def pix(v, w):
            return ((ra_per_tile * v + RA_OFFSET), (dec_per_tile * w + DEC_OFFSET))

        bottom_left = pix(tile.x, tile.y)
        top_right = pix(tile.x + 1, tile.y + 1)

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
