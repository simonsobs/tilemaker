"""
Cumulative information about data in an aperture.
"""

from time import perf_counter

import astropy.units as u
import numpy as np
from astropy.coordinates import ICRS
from astropydantic import AstroPydanticICRS, AstroPydanticQuantity
from structlog import get_logger

from tilemaker.analysis.core import AnalysisProvider, ProductNotFoundError
from tilemaker.metadata.core import DataConfiguration
from tilemaker.processing.extractor import extract
from tilemaker.providers.core import TileNotFoundError, Tiles

from .products import AnalysisProduct


class ApertureInformation(AnalysisProduct):
    layer_id: str

    position: AstroPydanticICRS
    radius: AstroPydanticQuantity[u.arcmin]

    mean: float | None = None
    std: float | None = None
    max: float | None = None
    min: float | None = None

    @property
    def hash(self):
        ra_deg = f"{self.position.ra.to_value(u.deg):08.4f}"
        dec_deg = f"{self.position.dec.to_value(u.deg):+07.4f}"
        return f"aperture-{self.layer_id}-{ra_deg}-{dec_deg}"

    def read(self, cache: AnalysisProvider, grants: set[str]):
        return cache.pull(self.hash, grants=grants, validate_type=ApertureInformation)

    def build(
        self,
        tiles: Tiles,
        metadata: DataConfiguration,
        cache: AnalysisProvider,
        grants: set[str],
    ):
        log = get_logger()

        log = log.bind(analysis_id=self.hash)

        try:
            return self.read(cache=cache, grants=grants)
        except ProductNotFoundError:
            pass

        layer = metadata.layer(layer_id=self.layer_id)

        if layer is None:
            log.debug("aperture.layer_not_found")
            raise TileNotFoundError(f"Layer {self.layer_id} not found")

        timing_start = perf_counter()

        top_right = ICRS(
            ra=self.position.ra + self.radius, dec=self.position.dec + self.radius
        )
        bottom_left = ICRS(
            ra=self.position.ra - self.radius, dec=self.position.dec - self.radius
        )

        cutout, push_tiles = extract(
            layer_id=self.layer_id,
            left=bottom_left.ra.to_value("deg"),
            right=top_right.ra.to_value("deg"),
            top=top_right.dec.to_value("deg"),
            bottom=bottom_left.dec.to_value("deg"),
            tiles=tiles,
            metadata=metadata,
            grants=grants,
            show_grid=False,
        )

        # Generate a circular mask
        y, x = np.ogrid[
            -cutout.shape[0] // 2 : cutout.shape[0] // 2,
            -cutout.shape[1] // 2 : cutout.shape[1] // 2,
        ]
        r = np.sqrt(x**2 + y**2)
        radius_pixels = len(cutout) / 2
        mask = r <= radius_pixels

        data_in_aperture = cutout[mask]
        data_in_aperture = data_in_aperture[~np.isnan(data_in_aperture)]

        if data_in_aperture.size == 0:
            log.debug("aperture.no_data")
            raise ProductNotFoundError("No data in aperture")

        self.mean = float(np.mean(data_in_aperture))
        self.std = float(np.std(data_in_aperture))
        self.max = float(np.max(data_in_aperture))
        self.min = float(np.min(data_in_aperture))
        self.grant = layer.grant

        timing_end = perf_counter()

        for tile in push_tiles:
            cache.push(tile)

        cache.push(self)

        log = log.bind(
            dt=timing_end - timing_start,
            n_tiles=len(push_tiles),
        )
        log.debug("aperture.built")

        return self
