"""
Map group - essentially an instruction to the frontend to group the maps together.

Example:

```json
{
  "name": "ACT DR6.02",
  "description": "Maps from DR6.02 from the Atacama Cosmology Telescope",
  "maps": [
    {
      "name": "ACT DR4 + DR6",
      "description": "Co-add between ACT DR6 and DR4 data.",
      "bands": [
        {
          "name": "f090",
          "description": "Frequency band f090",
          "layers": [
            {
              "name": "I",
              "description": "Intensity map",
              "provider": {
                "provider_type": "fits",
                "filename": "actdr4dr6.fits",
                "index": 0
              },
              "quantity": "T (I)",
              "units": "uK",
              "vmin": -500,
              "vmax": 500,
              "cmap": "RdBu_r"
            },
            {
              "name": "Q",
              "description": "Q-polarization map",
              "provider": {
                "provider_type": "fits",
                "filename": "actdr4dr6.fits",
                "index": 1
              },
              "quantity": "T (Q)",
              "units": "uK",
              "vmin": -50,
              "vmax": 50,
              "cmap": "RdBu_r"
            },
            {
              "name": "U",
              "description": "U-polarization map",
              "provider": {
                "provider_type": "fits",
                "filename": "actdr4dr6.fits",
                "index": 2
              },
              "quantity": "T (U)",
              "units": "uK",
              "vmin": -50,
              "vmax": 50,
              "cmap": "RdBu_r"
            }
          ]
        }
      ]
    }
  ]
}
```
"""

import math
from pathlib import Path
from typing import Literal

from astropy import units
from astropy.io import fits
from astropy.wcs import WCS
from pydantic import BaseModel


class AuthenticatedModel(BaseModel):
    grant: str | None = None

    def auth(self, grants: set[str]):
        return self.grant is None or self.grant in grants


class LayerProvider(BaseModel):
    provider_type: Literal["fits"] = "fits"

    def get_bbox(self) -> dict[str, float]:
        return


class FITSLayerProvider(LayerProvider):
    provider_type: Literal["fits"] = "fits"
    filename: Path
    hdu: int = 0
    index: int | None = None

    def get_bbox(self) -> dict[str, float]:
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
        with fits.open(self.filename) as h:
            return WCS(h[self.hdu].header)


class Layer(AuthenticatedModel):
    layer_id: str
    name: str
    description: str | None = None

    provider: FITSLayerProvider

    bounding_left: float | None = None
    bounding_right: float | None = None
    bounding_top: float | None = None
    bounding_bottom: float | None = None

    quantity: str | None = None
    units: str | None = None

    number_of_levels: int | None = None
    tile_size: int | None = None

    vmin: float | None = None
    vmax: float | None = None
    cmap: str | None = None

    def model_post_init(self, _):
        if self.bounding_left is None or self.bounding_right is None:
            bbox = self.provider.get_bbox()
            self.bounding_left = bbox["bounding_left"]
            self.bounding_right = bbox["bounding_right"]
            self.bounding_top = bbox["bounding_top"]
            self.bounding_bottom = bbox["bounding_bottom"]

        if self.tile_size is None or self.number_of_levels is None:
            self.tile_size, self.number_of_levels = self.provider.calculate_tile_size()


class Band(AuthenticatedModel):
    band_id: str
    name: str
    description: str

    layers: list[Layer]


class Map(AuthenticatedModel):
    map_id: str
    name: str
    description: str

    bands: list[Band]


class MapGroup(AuthenticatedModel):
    name: str
    description: str

    maps: list[Map]

    def get_layer(self, layer_id: str) -> Layer | None:
        for map in self.maps:
            for band in map.bands:
                for layer in band.layers:
                    if layer.layer_id == layer_id:
                        return layer

        return None
