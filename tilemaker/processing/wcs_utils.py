import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS


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

    x_size = int(round(abs(right - left) / cdelt1_mag))
    y_size = int(round(abs(top - bottom) / cdelt2_mag))

    bottom_left = SkyCoord(ra=left * u.deg, dec=bottom * u.deg)
    top_right = SkyCoord(ra=right * u.deg, dec=top * u.deg)

    # The header uses base_wcs's own CRPIX/CRVAL/LONPOLE/LATPOLE/CDELT-signs
    # completely unmodified (just re-anchored to CRVAL=(0, 0) -- see below),
    # not any re-derived values. Verified empirically against the real
    # full-sky layer's own tile-serving behavior (including with a gradient
    # marker to rule out mirroring): the tile-serving path
    # (`providers/fits.py::extract_patch_from_fits`, and the tile-index
    # remap in `server/layers.py`) reads straight from the FITS header's
    # own WCS, and only produces correct, level-independent, seamless
    # results when CRPIX/CDELT/LONPOLE/LATPOLE match a real base layer's
    # own values exactly -- re-deriving *any* of them (a synthetic
    # NAXIS/2-style CRPIX, a minimized/re-anchored CRPIX, a different
    # LONPOLE/LATPOLE) broke positioning beyond the lowest zoom level in
    # ways that were each individually hard to predict. This is the one
    # configuration that's actually been confirmed correct, even though it
    # costs more padding than a "minimal" CRPIX choice would.
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
    #
    # The written array starts at pixel 0 of base_wcs's own grid and spans
    # out to whichever pixel index is furthest from it -- either the
    # cutout's own far edge, or (if base_wcs's CRPIX itself sits beyond
    # the cutout) that reference point, since `extract_patch_from_fits`
    # treats `abs(CRPIX1) > NAXIS1` as a double-wrap sign and "corrects"
    # it, corrupting the projection if the array doesn't reach that far.
    naxis1_padded = int(np.ceil(max(px_bl, px_tr, ref_crpix1))) + 1
    naxis2_padded = int(np.ceil(max(py_bl, py_tr, ref_crpix2))) + 1
    data_offset_x = int(round(min(px_bl, px_tr)))
    data_offset_y = int(round(min(py_bl, py_tr)))

    submap_wcs = _ClientConventionWCS(naxis=2)
    submap_wcs.wcs.ctype = base_wcs.wcs.ctype
    submap_wcs.wcs.cunit = base_wcs.wcs.cunit
    submap_wcs.wcs.radesys = base_wcs.wcs.radesys
    submap_wcs.wcs.lonpole = ref_wcs.wcs.lonpole
    submap_wcs.wcs.latpole = ref_wcs.wcs.latpole

    submap_wcs.wcs.crval = ref_wcs.wcs.crval
    submap_wcs.wcs.crpix = [ref_crpix1, ref_crpix2]
    submap_wcs.wcs.cdelt = [ref_cdelt1, ref_cdelt2]

    # Carry the cutout size on the WCS itself (astropy's (NAXIS1, NAXIS2)
    # pixel_shape convention) so callers can recover it without a second
    # return value. Both axes are padded (see above); data_offset_x/y is
    # where the actual x_size x y_size cutout data should be written within
    # that wider/taller array.
    submap_wcs.pixel_shape = (naxis1_padded, naxis2_padded)
    submap_wcs.data_shape = (x_size, y_size)
    submap_wcs.data_offset_x = data_offset_x
    submap_wcs.data_offset_y = data_offset_y

    return submap_wcs
