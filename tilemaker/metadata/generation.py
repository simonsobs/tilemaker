"""
Create a set of metadata directly from a provider.
"""

from hashlib import md5
from pathlib import Path
from typing import Any

from astropy import units
from astropy.io import fits
from pydantic import BaseModel

from tilemaker.metadata.definitions import FITSLayerProvider, Layer


def layers_from_fits(
    filename: Path,
    force: str | None = None,
    unit_override: str | None = None,
) -> list[Layer]:
    data = fits.open(filename)

    if force:
        discriminator = DISCRIMINATORS[force]
    else:
        passed = False
        for discriminator in DISCRIMINATORS.values():
            passed = discriminator.check(data)
            if passed:
                break
        if not passed:
            raise ValueError(f"Unable to determine map type of {filename}")

    header = data[discriminator.hdu].header
    map_units = unit_override or header.get("BUNIT", None)

    layers = []

    for i, pl in enumerate(discriminator.proto_layers):
        layer_id = (
            f"{discriminator.hdu}-{i}-"
            + md5(str(filename).encode("utf-8")).hexdigest()[:6]
        )
        data = pl.convert_data(map_units=map_units)

        layers.append(
            Layer(
                layer_id=layer_id,
                **data,
                provider=FITSLayerProvider(
                    provider_type="fits",
                    filename=filename,
                    hdu=discriminator.hdu,
                    index=pl.index,
                ),
            )
        )

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
        map_units = map_units or self.units

        vmin = units.Quantity(self.vmin, unit=self.units)
        vmax = units.Quantity(self.vmax, unit=self.units)

        vmin = vmin.to_value(map_units)
        vmax = vmax.to_value(map_units)

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
    header_require: dict[str, Any]
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

        return True


DISCRIMINATORS = {
    "iqu": FITSDiscriminator(
        label="iqu",
        header_require={"POLCCONV": "IAU", "CTYPE3": "STOKES", "NAXIS3": 3},
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
    )
}
