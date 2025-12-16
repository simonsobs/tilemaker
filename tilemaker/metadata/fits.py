"""
FITS-based layer provider implementation.
"""

import math
from functools import reduce
from pathlib import Path
from typing import Literal

import numpy as np
from astropy import units
from astropy.io import fits
from astropy.wcs import WCS
from pydantic import BaseModel


class LayerProvider(BaseModel):
    """Base class for layer providers."""

    provider_type: Literal["fits"] = "fits"

    def get_bbox(self) -> dict[str, float]:
        """Get the bounding box of the provider."""
        return


class FITSLayerProvider(LayerProvider):
    """FITS file-based layer provider."""

    provider_type: Literal["fits"] = "fits"
    filename: Path
    hdu: int = 0
    index: int | None = None

    def get_bbox(self) -> dict[str, float]:
        """Extract bounding box from FITS file header."""
        with fits.open(self.filename) as handle:
            data = handle[self.hdu]
            wcs = WCS(header=data.header)

            top_right = wcs.array_index_to_world(*[0] * data.header.get("NAXIS", 2))
            bottom_left = wcs.array_index_to_world(*[x - 1 for x in data.data.shape])

            def sanitize(x):
                return (
                    x[0].ra
                    if x[0].ra < 180.0 * units.deg
                    else x[0].ra - 360.0 * units.deg
                ), (
                    x[0].dec
                    if x[0].dec < 90.0 * units.deg
                    else x[0].dec - 180.0 * units.deg
                )

            def sanitize_nonscalar(x):
                return x.ra if x.ra < 180.0 * units.deg else x.ra - 360.0 * units.deg, (
                    x.dec if x.dec < 90.0 * units.deg else x.dec - 180.0 * units.deg
                )

            try:
                tr = sanitize(top_right)
                bl = sanitize(bottom_left)
            except TypeError:
                tr = sanitize_nonscalar(top_right)
                bl = sanitize_nonscalar(bottom_left)

        return {
            "bounding_left": bl[0].value,
            "bounding_right": tr[0].value,
            "bounding_top": tr[1].value,
            "bounding_bottom": bl[1].value,
        }

    def calculate_tile_size(self) -> tuple[int, int]:
        """Calculate appropriate tile size based on FITS file properties."""
        # Need to figure out how big the whole 'map' is, i.e. moving it up
        # so that it fills the whole space.
        wcs = self.get_wcs()

        scale = wcs.proj_plane_pixel_scales()
        scale_x_deg = scale[0]
        scale_y_deg = scale[1]

        # The full sky spans 360 deg in RA, 180 deg in Dec
        map_size_x = int(math.floor(360 * units.deg / scale_x_deg))
        map_size_y = int(math.floor(180 * units.deg / scale_y_deg))

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

    def get_wcs(self) -> WCS:
        """Get the WCS object from the FITS file."""
        with fits.open(self.filename) as h:
            return WCS(h[self.hdu].header)


class FITSCombinationLayerProvider(LayerProvider):
    """
    Combination of multiple FITS files into a single layer. Takes as many layers
    as you like as inputs, and combines them in order using a simple function.

    For example, you could provide two FITS files and use the "/" function to
    find their ratio. Example:

    {
        "provider_type": "fits_combination",
        "providers": [
            {
                "provider_type": "fits",
                "filename": "file1.fits"
                "index": 2
            },
            {
                "provider_type": "fits",
                "filename": "file2.fits"
                "index": 3
            }
        ],
        "function": "/"
    }

    This would calculate: file1.fits[index=2] / file2.fits[index=3]
    """

    provider_type: Literal["fits_combination"] = "fits_combination"
    providers: list[FITSLayerProvider]
    function: Literal["+", "-", "*", "/", "max", "min", "mean"] = "/"

    def get_bbox(self) -> dict[str, float]:
        """Get the bounding box from the underlying providers. If
        they differ, we crash."""

        bboxes = [p.get_bbox() for p in self.providers]
        first_bbox = bboxes[0]
        for bbox in bboxes[1:]:
            if bbox != first_bbox:
                raise ValueError(
                    "Bounding boxes of combined FITS providers do not match."
                )

        return first_bbox

    def calculate_tile_size(self) -> tuple[int, int]:
        """Calculate tile size from each provider, and make sure they match."""
        tile_sizes = [p.calculate_tile_size() for p in self.providers]
        first_size = tile_sizes[0]
        for size in tile_sizes[1:]:
            if size != first_size:
                raise ValueError("Tile sizes of combined FITS providers do not match.")

        return first_size

    def get_wcs(self) -> WCS:
        """Get the WCS from the first provider."""
        return self.providers[0].get_wcs()

    def chain(self, arrays: list[np.ndarray]) -> np.ndarray:
        """Chain the arrays together using the specified function."""
        if not arrays:
            raise ValueError("No arrays provided for combination.")

        if all(x is None for x in arrays):
            return None

        func = {
            "+": np.add,
            "-": np.subtract,
            "*": np.multiply,
            "/": np.divide,
            "max": np.maximum,
            "min": np.minimum,
            "mean": lambda x, y: (x + y) / 2,
        }

        # Handle None values (i.e. when maps contain no information)
        # with an appropiate neutral element.
        none_handler = {
            "+": 0.0,
            "-": 0.0,
            "*": 1.0,
            "/": 1.0,
            "max": -np.inf,
            "min": np.inf,
            "mean": 0.0,
        }

        return reduce(
            func[self.function],
            [x if x is not None else none_handler[self.function] for x in arrays],
        )
