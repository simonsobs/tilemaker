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

from pathlib import Path
from typing import Literal
from pydantic import BaseModel


class LayerProvider(BaseModel):
    provider_type: Literal["fits"] = "fits"


class FITSLayerProvider(LayerProvider):
    provider_type: Literal["fits"] = "fits"
    filename: Path
    hdu: int = 0
    index: int | None = None


class Layer(BaseModel):
    name: str
    description: str
    grant: str | None = None

    provider: LayerProvider
    
    bounding_left: float | None = None
    bounding_right: float | None = None
    bounding_top: float | None = None
    bounding_bottom: float | None = None

    quantity: str | None = None
    units: str | None = None

    vmin: float | None = None
    vmax: float | None = None
    cmap: str | None = None


class Band(BaseModel):
    name: str
    description: str
    grant: str | None = None

    layers: list[Layer]


class Map(BaseModel):
    name: str
    description: str
    grant: str | None = None

    bands: list[Band]


class MapGroup(BaseModel):
    name: str
    description: str
    grant: str | None = None

    maps: list[Map]




