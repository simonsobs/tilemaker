import math

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

from tilemaker.metadata.fits import tile_size_for_scale

# How many multiples of the tile pyramid's coarsest subsample stride to pad
# by, beyond the bare minimum needed to keep subsample phase aligned (see
# the comment in build_submap_wcs below). A larger margin costs a bit more
# file size but absorbs edge effects at the very coarsest zoom levels for
# large/off-center cutouts.
_PADDING_SAFETY_MARGIN = 4


class _CoordResult:
    """Minimal ra/dec container. SkyCoord's constructor always re-wraps RA
    to astropy's default [0, 360) range, discarding any custom wrap_angle,
    so it can't be used to carry a -180..180 RA value through untouched."""

    __slots__ = ("ra", "dec")

    def __init__(self, ra, dec):
        self.ra = ra
        self.dec = dec


class _ClientConventionWCS(WCS):
    """A WCS whose pixel_to_world reports RA in -180..180 (client
    convention) rather than astropy's default 0..360, since that's the
    convention build_submap_wcs's left/right/CRVAL inputs are given in."""

    def pixel_to_world(self, *pixel_arrays):
        coord = super().pixel_to_world(*pixel_arrays)
        return _CoordResult(coord.ra.wrap_at(180 * u.deg), coord.dec)


def build_submap_wcs(
    left: float,
    right: float,
    top: float,
    bottom: float,
    base_wcs: WCS,
) -> WCS:
    """
    Build a WCS for a submap cutout.

    Parameters
    ----------
    left, right : float
        RA bounds in degrees (client convention, e.g. -180 to 180)
    top, bottom : float
        Dec bounds in degrees
    base_wcs : WCS
        The full-sky base WCS from the layer provider

    Returns
    -------
    submap_wcs : WCS
        `submap_wcs.pixel_shape` is the padded array shape the header
        describes (see below). `submap_wcs.data_shape` is the actual
        (x_size, y_size) of the requested cutout, and
        `data_offset_x`/`data_offset_y` is where that data should be
        written within an array sized `pixel_shape`.
    """
    # base_wcs may come straight from a FITS header with extra axes
    # (frequency, Stokes, ...); reduce to the 2D celestial sub-WCS so
    # crpix/crval/cdelt below always have exactly 2 elements.
    base_wcs = base_wcs.celestial

    cdelt_ra = base_wcs.wcs.cdelt[0]
    cdelt_dec = base_wcs.wcs.cdelt[1]
    cdelt1_mag = abs(cdelt_ra)
    cdelt2_mag = abs(cdelt_dec)

    x_size = round(abs(right - left) / cdelt1_mag)
    y_size = round(abs(top - bottom) / cdelt2_mag)

    bottom_left = SkyCoord(ra=left * u.deg, dec=bottom * u.deg)
    top_right = SkyCoord(ra=right * u.deg, dec=top * u.deg)

    # The header uses base_wcs's own CRPIX/CRVAL/LONPOLE/LATPOLE/CDELT-signs
    # completely unmodified (just re-anchored to CRVAL=(0, 0) -- see below),
    # not any re-derived values, other than a whole-pixel shift applied
    # below to both CRPIX and the array origin together. Verified
    # empirically against the real full-sky layer's own tile-serving
    # behavior (including with a gradient marker to rule out mirroring):
    # the tile-serving path (`providers/fits.py::extract_patch_from_fits`)
    # reads straight from the FITS header's own WCS, and only produces
    # correct, level-independent, seamless results when CRPIX/CDELT/
    # LONPOLE/LATPOLE match a real base layer's own values exactly modulo a
    # whole multiple of the tile pyramid's coarsest subsample stride (see
    # below) -- shifting by anything else broke positioning beyond the
    # lowest zoom level in ways that were each individually hard to
    # predict, because `extract_patch_from_fits`'s subsampling picks its
    # phase from the *absolute* pixel position of each request.
    ref_wcs = base_wcs.deepcopy()
    ref_wcs.wcs.crval = [0.0, 0.0]

    ref_crpix1, ref_crpix2 = ref_wcs.wcs.crpix
    ref_cdelt1, ref_cdelt2 = ref_wcs.wcs.cdelt

    px_bl, py_bl = ref_wcs.world_to_pixel(bottom_left)
    px_tr, py_tr = ref_wcs.world_to_pixel(top_right)
    px_bl, py_bl, px_tr, py_tr = float(px_bl), float(py_bl), float(px_tr), float(py_tr)

    # Which world corner ends up at the smaller pixel index isn't something
    # this function decides -- it falls out of base_wcs's own convention
    # (its CDELT signs combined with its LONPOLE/LATPOLE), and is left
    # alone rather than forced into a fixed orientation.
    raw_offset_x = round(min(px_bl, px_tr))
    raw_offset_y = round(min(py_bl, py_tr))

    # A submap FITS file gets re-ingested as a brand-new layer via
    # `tilemaker open`, whose own tile pyramid depth is re-derived from
    # scratch purely from pixel scale (FITSLayerProvider.calculate_tile_size,
    # which shares tile_size_for_scale with this function) -- so it always
    # matches what we compute here, independent of the *source* layer's own
    # (possibly config-overridden) number_of_levels.
    #
    # FITSTileProvider.pull() requests native pixels at subsample stride
    # 2**(number_of_levels - 1 - level), whose coarsest value is
    # 2**(number_of_levels - 1). extract_array/overlap_slices pick which
    # native pixels land in a given subsampled tile based on the *absolute*
    # pixel position of the request, so shifting CRPIX (and the array's
    # pixel-0 origin) by anything that isn't a whole multiple of that
    # coarsest stride changes which native pixels a coarse-zoom tile reads
    # -- scrambling positioning at every level except the finest. Padding
    # to a whole multiple of the stride (with a small safety margin,
    # _PADDING_SAFETY_MARGIN) keeps the same subsample phase as base_wcs's
    # own (unshifted) grid at every level, without needing to pad all the
    # way out to a full-sky-sized array. This applies identically to both
    # axes -- the tile-index "flip" fold (server/layers.py::get_tile) and
    # its per-tile mirror (processing/renderer.py) only remap an abstract
    # tile index derived from a hardcoded virtual full-sky grid
    # (FITSTileProvider._get_tile_info); they never read CRPIX/NAXIS, so
    # they need no special-casing here at all.
    _, number_of_levels = tile_size_for_scale(cdelt1_mag * u.deg, cdelt2_mag * u.deg)
    stride = max(1, 2 ** (number_of_levels - 1))
    pad = _PADDING_SAFETY_MARGIN * stride

    # Defensive upper bound: never pad past the size a genuine full-sky
    # array would have at this pixel scale (what today's export used
    # unconditionally) -- this keeps aligned_far_* sane even if `pad` were
    # ever unexpectedly large relative to the cutout.
    max_naxis_x = round(360.0 / cdelt1_mag)
    max_naxis_y = round(180.0 / cdelt2_mag)

    aligned_offset_x = max(0, (raw_offset_x // pad) * pad)
    aligned_offset_y = max(0, (raw_offset_y // pad) * pad)
    aligned_far_x = min(max_naxis_x, math.ceil((raw_offset_x + x_size) / pad) * pad)
    aligned_far_y = min(max_naxis_y, math.ceil((raw_offset_y + y_size) / pad) * pad)

    naxis1 = aligned_far_x - aligned_offset_x
    naxis2 = aligned_far_y - aligned_offset_y

    submap_wcs = _ClientConventionWCS(naxis=2)
    submap_wcs.wcs.ctype = base_wcs.wcs.ctype
    submap_wcs.wcs.cunit = base_wcs.wcs.cunit
    submap_wcs.wcs.radesys = base_wcs.wcs.radesys
    submap_wcs.wcs.lonpole = ref_wcs.wcs.lonpole
    submap_wcs.wcs.latpole = ref_wcs.wcs.latpole

    submap_wcs.wcs.crval = ref_wcs.wcs.crval
    submap_wcs.wcs.crpix = [
        ref_crpix1 - aligned_offset_x,
        ref_crpix2 - aligned_offset_y,
    ]
    submap_wcs.wcs.cdelt = [ref_cdelt1, ref_cdelt2]

    # Carry the cutout size on the WCS itself (astropy's (NAXIS1, NAXIS2)
    # pixel_shape convention) so callers can recover it without a second
    # return value. Both axes are padded out to a stride-aligned boundary
    # (see above); data_offset_x/y is where the actual x_size x y_size
    # cutout data should be written within that array.
    submap_wcs.pixel_shape = (naxis1, naxis2)
    submap_wcs.data_shape = (x_size, y_size)
    submap_wcs.data_offset_x = raw_offset_x - aligned_offset_x
    submap_wcs.data_offset_y = raw_offset_y - aligned_offset_y

    return submap_wcs
