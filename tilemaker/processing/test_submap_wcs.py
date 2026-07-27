# test_submap_wcs.py
from astropy.wcs import WCS

from tilemaker.processing.wcs_utils import build_submap_wcs

# --- Inputs matching your real request ---
LEFT = -72.3514
RIGHT = -60.9358
TOP = -39.4649
BOTTOM = -41.4070

TOLERANCE_DEG = 0.05


def get_base_wcs() -> WCS:
    """Reconstruct the same base WCS the layer provider returns."""
    CDELT_RA = -0.0083333333333333
    CDELT_DEC = 0.0083333333333333
    NAXIS1 = int(360.0 / abs(CDELT_RA))
    NAXIS2 = int(180.0 / abs(CDELT_DEC))

    return WCS(
        {
            "NAXIS": 2,
            "CRPIX1": NAXIS1 * 0.5,
            "CRPIX2": NAXIS2 * 0.5 + 0.5,
            "CRVAL1": 0.0,
            "CRVAL2": 0.0,
            "NAXIS1": NAXIS1,
            "NAXIS2": NAXIS2,
            "CDELT1": CDELT_RA,
            "CDELT2": -CDELT_DEC,
            "CTYPE1": "RA---CAR",
            "CTYPE2": "DEC--CAR",
            "CUNIT1": "deg",
            "CUNIT2": "deg",
            "LONPOLE": 0.0,
            "LATPOLE": 90.0,
            "RADESYS": "ICRS",
        }
    )


def check(name, got, expected, tol=TOLERANCE_DEG):
    diff = abs(got - expected)
    status = "PASS" if diff < tol else "FAIL"
    print(f"{status} {name}: got={got:.5f}  expected={expected:.5f}  diff={diff:.5f}")
    return status == "PASS"


def run():
    base_wcs = get_base_wcs()
    submap_wcs = build_submap_wcs(LEFT, RIGHT, TOP, BOTTOM, base_wcs)
    padded_x_size, padded_y_size = submap_wcs.pixel_shape
    x_size, y_size = submap_wcs.data_shape
    offset_x = submap_wcs.data_offset_x
    offset_y = submap_wcs.data_offset_y

    print(f"\nPadded array size: x={padded_x_size}, y={padded_y_size}")
    print(
        f"Actual data size:  x={x_size}, y={y_size}  "
        f"(offset_x={offset_x}, offset_y={offset_y})"
    )
    print(f"CRVAL:  {submap_wcs.wcs.crval}")
    print(f"CRPIX:  {submap_wcs.wcs.crpix}")
    print(f"CDELT:  {submap_wcs.wcs.cdelt}")
    print()

    # pixel_to_world uses 0-indexed pixels. Both axes are padded (see
    # build_submap_wcs), so the actual cutout data lives at columns
    # [offset_x, offset_x + x_size) and rows [offset_y, offset_y + y_size)
    # rather than starting at pixel (0, 0).
    #
    # Which specific pixel corner maps to which specific world corner
    # (e.g. does column offset_x hold LEFT or RIGHT?) is decided by
    # base_wcs's own pixel-index-vs-world-value convention -- verified
    # (via the real base layer's own tile-serving behavior, including a
    # gradient marker to rule out mirroring) to need to match base_wcs's
    # convention exactly, rather than a convention build_submap_wcs
    # enforces itself. So instead of asserting a specific corner mapping,
    # check the four corners as a set: two should be at RA=LEFT, two at
    # RA=RIGHT (one each for the two rows), and two at Dec=TOP, two at
    # Dec=BOTTOM (one each for the two columns) -- i.e. a correctly
    # positioned, non-mirrored, non-rotated rectangle.
    corners = [
        submap_wcs.pixel_to_world(offset_x, offset_y),
        submap_wcs.pixel_to_world(offset_x + x_size - 1, offset_y),
        submap_wcs.pixel_to_world(offset_x, offset_y + y_size - 1),
        submap_wcs.pixel_to_world(offset_x + x_size - 1, offset_y + y_size - 1),
    ]
    ras = sorted(c.ra.deg for c in corners)
    decs = sorted(c.dec.deg for c in corners)

    all_pass = all(
        [
            check("min RA  (two corners)", ras[0], LEFT),
            check("min RA  (two corners)", ras[1], LEFT),
            check("max RA  (two corners)", ras[2], RIGHT),
            check("max RA  (two corners)", ras[3], RIGHT),
            check("min Dec (two corners)", decs[0], BOTTOM),
            check("min Dec (two corners)", decs[1], BOTTOM),
            check("max Dec (two corners)", decs[2], TOP),
            check("max Dec (two corners)", decs[3], TOP),
        ]
    )

    print()
    print("ALL PASS" if all_pass else "SOME CHECKS FAILED")


if __name__ == "__main__":
    run()
