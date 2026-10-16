"""
Tests for build_submap_wcs, covering both correct positioning of the
cutout and the stride-aligned padding scheme that replaced padding the RA
axis out to a full-sky-sized array (see processing/wcs_utils.py).
"""

import tempfile
from pathlib import Path

import astropy.units as u
import numpy as np
import pytest
import structlog
from astropy.io import fits
from astropy.wcs import WCS

from tilemaker.metadata.fits import FITSLayerProvider, tile_size_for_scale
from tilemaker.processing.wcs_utils import _PADDING_SAFETY_MARGIN, build_submap_wcs
from tilemaker.providers.core import PullableTile
from tilemaker.providers.fits import FITSTileProvider, extract_patch_from_fits

LOG = structlog.get_logger()

# A base layer at ~0.176 deg/pixel: NAXIS1=2048, NAXIS2=1024, which lands on
# the "clean 256" branch of tile_size_for_scale and yields a 4-level
# pyramid (levels 0-3, coarsest subsample stride = 2**(4-1) = 8) -- enough
# levels to meaningfully exercise stride-phase alignment while staying
# small/fast.
NAXIS1 = 2048
NAXIS2 = 1024
CDELT = 360.0 / NAXIS1


def _base_wcs() -> WCS:
    return WCS(
        {
            "NAXIS": 2,
            "CRPIX1": NAXIS1 * 0.5,
            "CRPIX2": NAXIS2 * 0.5 + 0.5,
            "CRVAL1": 0.0,
            "CRVAL2": 0.0,
            "NAXIS1": NAXIS1,
            "NAXIS2": NAXIS2,
            "CDELT1": -CDELT,
            "CDELT2": CDELT,
            "CTYPE1": "RA---CAR",
            "CTYPE2": "DEC--CAR",
            "CUNIT1": "deg",
            "CUNIT2": "deg",
            "LONPOLE": 0.0,
            "LATPOLE": 90.0,
            "RADESYS": "ICRS",
        }
    )


# A small cutout close to (RA, Dec) = (180, -90), which for this base WCS
# (CRVAL=(0,0), CRPIX at the array midpoint) lands close to native pixel
# (0, 0) -- keeps the synthetic "base layer" array small in the tile-serving
# regression test below while still exercising a real, non-trivial pixel
# offset (not exactly zero).
LEFT, RIGHT = 176.0, 179.0
BOTTOM, TOP = -89.0, -86.0


def test_build_submap_wcs_places_corners_correctly():
    """The four corners of the cutout should land at (LEFT/RIGHT, TOP/BOTTOM),
    not mirrored or rotated."""
    base_wcs = _base_wcs()
    submap_wcs = build_submap_wcs(LEFT, RIGHT, TOP, BOTTOM, base_wcs)

    x_size, y_size = submap_wcs.data_shape
    offset_x, offset_y = submap_wcs.data_offset_x, submap_wcs.data_offset_y

    corners = [
        submap_wcs.pixel_to_world(offset_x, offset_y),
        submap_wcs.pixel_to_world(offset_x + x_size - 1, offset_y),
        submap_wcs.pixel_to_world(offset_x, offset_y + y_size - 1),
        submap_wcs.pixel_to_world(offset_x + x_size - 1, offset_y + y_size - 1),
    ]
    ras = sorted(c.ra.deg for c in corners)
    decs = sorted(c.dec.deg for c in corners)

    # left/right/top/bottom get rounded to the nearest whole pixel (see
    # x_size/y_size in build_submap_wcs), so allow slack of a couple of
    # pixels at this test's coarse (~0.18 deg/pixel) synthetic resolution.
    tol = 2 * CDELT
    assert ras[0] == pytest.approx(LEFT, abs=tol)
    assert ras[1] == pytest.approx(LEFT, abs=tol)
    assert ras[2] == pytest.approx(RIGHT, abs=tol)
    assert ras[3] == pytest.approx(RIGHT, abs=tol)
    assert decs[0] == pytest.approx(BOTTOM, abs=tol)
    assert decs[1] == pytest.approx(BOTTOM, abs=tol)
    assert decs[2] == pytest.approx(TOP, abs=tol)
    assert decs[3] == pytest.approx(TOP, abs=tol)


def test_build_submap_wcs_padding_is_stride_aligned_not_full_sky():
    """The whole point of the fix: padding should be a small, bounded
    multiple of the tile pyramid's coarsest subsample stride, not a
    full-360-degree-wide array."""
    base_wcs = _base_wcs()
    submap_wcs = build_submap_wcs(LEFT, RIGHT, TOP, BOTTOM, base_wcs)

    _, number_of_levels = tile_size_for_scale(CDELT * u.deg, CDELT * u.deg)
    stride = 2 ** (number_of_levels - 1)
    pad = _PADDING_SAFETY_MARGIN * stride

    naxis1, naxis2 = submap_wcs.pixel_shape
    x_size, y_size = submap_wcs.data_shape

    # Padded array must be much smaller than a full-sky-sized array would
    # have been (the old behavior padded NAXIS1 to 360 / cdelt ~= NAXIS1).
    assert naxis1 < NAXIS1 // 4
    assert naxis2 < NAXIS2 // 4

    # But still a whole multiple of `pad` (so CRPIX lands on a stride-
    # aligned boundary), and big enough to hold the actual cutout.
    assert naxis1 % pad == 0
    assert naxis2 % pad == 0
    assert naxis1 >= x_size
    assert naxis2 >= y_size

    # CRPIX must have shifted by a whole multiple of `pad` relative to the
    # base layer's own CRPIX -- that's what keeps subsample phase aligned
    # with the source layer's own grid at every zoom level.
    base_crpix1, base_crpix2 = base_wcs.wcs.crpix
    shift_x = base_crpix1 - submap_wcs.wcs.crpix[0]
    shift_y = base_crpix2 - submap_wcs.wcs.crpix[1]
    assert shift_x % pad == 0
    assert shift_y % pad == 0


def _flip_tile_x(x: int, level: int) -> int:
    """Mirrors the tile-index fold in server/layers.py::get_tile."""
    if level == 0:
        return x
    midpoint = 2**level
    if x < midpoint:
        return (2**level - 1) - x
    return (2**level - 1) - (x - midpoint) + midpoint


def test_submap_tile_serving_matches_base_layer_pixels():
    """Re-ingesting a submap export and serving tiles from it (at any zoom
    level, with or without `flip`) must reproduce the same native pixel
    values the *source* layer would have served for the same sky location.

    This is a regression test for the stride-phase bug found during
    investigation: a naive "minimal CRPIX" cutout reproduces the correct
    pixels only at the finest zoom level, and silently reads the wrong
    native pixels (a phase-shifted subsample) at every coarser level.
    """
    base_wcs = _base_wcs()
    submap_wcs = build_submap_wcs(LEFT, RIGHT, TOP, BOTTOM, base_wcs)

    naxis1, naxis2 = submap_wcs.pixel_shape
    x_size, y_size = submap_wcs.data_shape
    data_offset_x, data_offset_y = submap_wcs.data_offset_x, submap_wcs.data_offset_y

    base_crpix1, base_crpix2 = base_wcs.wcs.crpix
    aligned_offset_x = round(base_crpix1 - submap_wcs.wcs.crpix[0])
    aligned_offset_y = round(base_crpix2 - submap_wcs.wcs.crpix[1])

    # A lightweight stand-in for the base layer's real array: only the
    # small local footprint the padded submap actually touches (this test's
    # LEFT/RIGHT/BOTTOM/TOP were chosen close to native pixel (0, 0) so this
    # stays small), encoded with each pixel's own native (x, y) index so any
    # phase shift in subsampling shows up as a wrong value rather than
    # coincidentally matching.
    margin = 4
    footprint_x = aligned_offset_x + naxis1 + margin
    footprint_y = aligned_offset_y + naxis2 + margin
    assert footprint_x < 500 and footprint_y < 500, (
        "test cutout constants no longer land near native pixel (0, 0); "
        "the synthetic base array would be unexpectedly large"
    )

    base_data = (
        np.arange(footprint_x, dtype=np.float64)[None, :] * 100_000
        + np.arange(footprint_y, dtype=np.float64)[:, None]
    )

    submap_data = np.full((naxis2, naxis1), np.nan)
    submap_data[
        data_offset_y : data_offset_y + y_size, data_offset_x : data_offset_x + x_size
    ] = base_data[
        aligned_offset_y + data_offset_y : aligned_offset_y + data_offset_y + y_size,
        aligned_offset_x + data_offset_x : aligned_offset_x + data_offset_x + x_size,
    ]

    base_header = base_wcs.to_header()
    submap_header = submap_wcs.to_header()

    _, number_of_levels = tile_size_for_scale(CDELT * u.deg, CDELT * u.deg)
    provider = FITSTileProvider.__new__(FITSTileProvider)

    mismatches = []
    tested_any = False
    for flip in (False, True):
        for level in range(number_of_levels):
            subsample_every = 2 ** (number_of_levels - level - 1)
            n_tiles_x = 2 ** (level + 1)
            n_tiles_y = 2**level
            for display_x in range(n_tiles_x):
                for y in range(n_tiles_y):
                    fetch_x = _flip_tile_x(display_x, level) if flip else display_x
                    info = provider._get_tile_info(
                        PullableTile(
                            layer_id="test", x=fetch_x, y=y, level=level, grants=None
                        )
                    )

                    # Only test tiles that overlap the cutout at all --
                    # elsewhere both sides are legitimately all-NaN/absent.
                    ra0, ra1 = sorted(info["ra_range"])
                    dec0, dec1 = sorted(info["dec_range"])
                    if ra1 < LEFT or ra0 > RIGHT or dec1 < BOTTOM or dec0 > TOP:
                        continue

                    base_hdu = fits.PrimaryHDU(base_data, header=base_header.copy())
                    submap_hdu = fits.PrimaryHDU(
                        submap_data, header=submap_header.copy()
                    )

                    base_patch = extract_patch_from_fits(
                        hdu=base_hdu, subsample_every=subsample_every, log=LOG, **info
                    )
                    submap_patch = extract_patch_from_fits(
                        hdu=submap_hdu,
                        subsample_every=subsample_every,
                        log=LOG,
                        **info,
                    )
                    tested_any = True

                    if base_patch.shape != submap_patch.shape:
                        mismatches.append((flip, level, display_x, y, "shape mismatch"))
                        continue

                    both_finite = np.isfinite(base_patch) & np.isfinite(submap_patch)
                    if not both_finite.any():
                        continue
                    if not np.array_equal(
                        base_patch[both_finite], submap_patch[both_finite]
                    ):
                        mismatches.append((flip, level, display_x, y, "value mismatch"))

    assert tested_any, "no tiles overlapped the test cutout -- test setup is broken"
    assert not mismatches, f"{len(mismatches)} tile mismatch(es): {mismatches[:10]}"


def test_get_bbox_recovers_tight_bounds_not_whole_sky():
    """A re-ingested submap layer's reported bounding box should be close
    to the requested cutout, not the entire sky -- a bug the old full-sky
    padding caused as a side effect (CRPIX left unmodified inside an array
    padded out to a full-sky width made the corner pixels of the *padded*
    array read out as +/-180 RA, +/-90 Dec)."""
    base_wcs = _base_wcs()
    submap_wcs = build_submap_wcs(LEFT, RIGHT, TOP, BOTTOM, base_wcs)

    naxis1, naxis2 = submap_wcs.pixel_shape
    data = np.zeros((naxis2, naxis1), dtype=np.float64)
    header = submap_wcs.to_header()
    hdu = fits.PrimaryHDU(data, header=header)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "submap.fits"
        hdu.writeto(path)

        provider = FITSLayerProvider(filename=path)
        bbox = provider.get_bbox()

    pad_deg = (
        _PADDING_SAFETY_MARGIN
        * 2 ** (tile_size_for_scale(CDELT * u.deg, CDELT * u.deg)[1] - 1)
        * CDELT
    )

    assert bbox["bounding_left"] == pytest.approx(LEFT, abs=pad_deg + 0.1)
    assert bbox["bounding_right"] == pytest.approx(RIGHT, abs=pad_deg + 0.1)
    assert bbox["bounding_top"] == pytest.approx(TOP, abs=pad_deg + 0.1)
    assert bbox["bounding_bottom"] == pytest.approx(BOTTOM, abs=pad_deg + 0.1)
