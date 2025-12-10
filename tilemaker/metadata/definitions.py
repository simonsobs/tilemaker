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

from typing import Literal

from pydantic import BaseModel

from .fits import FITSLayerProvider


class AuthenticatedModel(BaseModel):
    grant: str | None = None

    def auth(self, grants: set[str]):
        return self.grant is None or self.grant in grants


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

    vmin: float | Literal["auto"] | None = None
    vmax: float | Literal["auto"] | None = None
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
