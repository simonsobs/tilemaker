"""
Create a set of metadata directly from a provider.
"""

import os
from hashlib import md5
from pathlib import Path
from typing import Any

import structlog
from astropy import units
from astropy.io import fits
from pydantic import BaseModel

from tilemaker.metadata.core import DataConfiguration
from tilemaker.metadata.definitions import Band, FITSLayerProvider, Layer, Map, MapGroup

# Define the hits unit
hits = units.def_unit("hits", units.dimensionless_unscaled)
units.add_enabled_units([hits])


def generate(filenames: list[Path]):
    map_files = [x for x in filenames if "fits" in x.name]
    map_group = map_group_from_fits(map_files)

    return DataConfiguration(map_groups=[map_group], boxes=[], source_groups=[])


def filename_to_id(filename: str | Path) -> str:
    return md5(str(filename).encode("utf-8")).hexdigest()[:6]


def map_group_from_fits(
    filenames: list[Path],
):
    maps = []
    for filename in filenames:
        filename = Path(filename)
        maps.append(
            Map(
                map_id=filename_to_id(filename),
                name=filename.name,
                description="No description",
                bands=[
                    Band(
                        band_id=f"band-{filename_to_id(filename)}",
                        name="Auto-Populated",
                        description="Auto-populated band",
                        layers=layers_from_fits(filename=filename),
                    )
                ],
            )
        )

    return MapGroup(
        name="Auto-Populated", description="No description provided", maps=maps
    )


def layers_from_fits(
    filename: Path,
    force: str | None = None,
    unit_override: str | None = None,
) -> list[Layer]:
    log = structlog.get_logger()
    log = log.bind(filename=str(filename))
    data = fits.open(filename)

    if force:
        log = log.bind(discriminator=force)
        discriminator = DISCRIMINATORS[force]
    else:
        passed = False
        for discriminator in DISCRIMINATORS.values():
            passed = discriminator.check(data)
            if passed:
                log = log.bind(discriminator=discriminator.label)
                log.info("discriminator.passed")
                break
        if not passed:
            log.warning("discrimination.failed")
            discriminator = FITSDiscriminator(
                label="unknown",
                proto_layers=[
                    ProtoLayer(
                        name="Layer",
                        description="Unknown layer",
                        quantity=None,
                        units=None,
                        vmin=-1.0,
                        vmax=1.0,
                        cmap="viridis",
                        index=None,
                    )
                ],
            )
            unit_override = "unk"

    header = data[discriminator.hdu].header
    map_units = unit_override or header.get("BUNIT", None)

    layers = []

    for i, pl in enumerate(discriminator.proto_layers):
        layer_id = f"{discriminator.hdu}-{i}-" + filename_to_id(filename)
        log = log.bind(layer_id=layer_id)
        data = pl.convert_data(map_units=map_units)

        layers.append(
            Layer(
                layer_id=layer_id,
                **data,
                provider=FITSLayerProvider(
                    provider_type="fits",
                    filename=Path(filename).absolute(),
                    hdu=discriminator.hdu,
                    index=pl.index,
                ),
            )
        )
        log.info("layer.success")

    return layers


class ProtoLayer(BaseModel):
    name: str
    description: str | None = None
    quantity: str | None = None
    units: str | None = None
    vmin: float | None = None
    vmax: float | None = None
    cmap: str | None = None
    index: int | None = None

    def convert_data(self, map_units: str | None):
        if map_units != "unk":
            map_units = map_units or self.units

            vmin = units.Quantity(self.vmin, unit=self.units)
            vmax = units.Quantity(self.vmax, unit=self.units)

            vmin = vmin.to_value(map_units)
            vmax = vmax.to_value(map_units)
        else:
            vmin = self.vmin
            vmax = self.vmax

        return {
            "name": self.name,
            "description": self.description,
            "quantity": self.quantity,
            "vmin": vmin,
            "vmax": vmax,
            "units": map_units,
            "cmap": self.cmap,
        }


class FITSDiscriminator(BaseModel):
    hdu: int = 0
    label: str
    filename_contains: list[str] = []
    header_require: dict[str, Any] = {}
    proto_layers: list[ProtoLayer]

    def check(self, data: fits.HDUList) -> bool:
        try:
            header = data[self.hdu].header
        except IndexError:
            return False

        for k, v in self.header_require.items():
            value = header.get(k, None)

            if not value or value != v:
                return False

        if not self.filename_contains:
            return True

        for item in self.filename_contains:
            if item in os.path.basename(data.filename()):
                return True

        return False


DISCRIMINATORS = {
    "iqu": FITSDiscriminator(
        label="iqu",
        header_require={"NAXIS3": 3},
        proto_layers=[
            ProtoLayer(
                name="I",
                description="Intensity map",
                quantity="I",
                units="uK",
                vmin=-500.0,
                vmax=500.0,
                cmap="RdBu_r",
                index=0,
            ),
            ProtoLayer(
                name="Q",
                description="Q-polarization map",
                quantity="Q",
                units="uK",
                vmin=-50.0,
                vmax=50.0,
                cmap="RdBu_r",
                index=1,
            ),
            ProtoLayer(
                name="U",
                description="U-polarization map",
                quantity="U",
                units="uK",
                vmin=-50.0,
                vmax=50.0,
                cmap="RdBu_r",
                index=2,
            ),
        ],
    ),
    "ivar": FITSDiscriminator(
        label="ivar",
        filename_contains=["ivar", "div"],
        proto_layers=[
            ProtoLayer(
                name="IVar",
                description="Inverse-variance map",
                quantity="ivar",
                units="K^-2",
                vmin=100000000.0,
                vmax=2000000000.0,
                cmap="inferno",
                index=None,
            )
        ],
    ),
    "mask": FITSDiscriminator(
        label="mask",
        filename_contains=["mask"],
        proto_layers=[
            ProtoLayer(
                name="Mask",
                description="Sky mask",
                quantity="mask",
                units=None,
                vmin=0.0,
                vmax=1.0,
                cmap="viridis",
                index=None,
            )
        ],
    ),
    "hits": FITSDiscriminator(
        label="hits",
        filename_contains=["hits"],
        proto_layers=[
            ProtoLayer(
                name="Hits",
                description="Hits map",
                quantity="n",
                units=" ",
                vmin=0.0,
                vmax=100.0,
                cmap="viridis",
                index=None,
            )
        ],
    ),
}
