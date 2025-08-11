"""
Histogram generation and storage.
"""

from time import perf_counter

import numpy as np
import structlog

from tilemaker.metadata.core import DataConfiguration
from tilemaker.providers.core import PullableTile, TileNotFoundError, Tiles

from .products import AnalysisProduct


class HistogramProduct(AnalysisProduct):
    layer_id: str

    counts: list[int]
    edges: list[float]

    @property
    def hash(self):
        return f"hist-{self.layer_id}"

    @classmethod
    def build(
        cls, tiles: Tiles, metadata: DataConfiguration, analysis_id: str
    ) -> "HistogramProduct":
        log = structlog.get_logger()

        layer_id = analysis_id.replace("hist-", "")

        log = log.bind(layer_id=layer_id)

        layer = metadata.layer(layer_id=layer_id)

        if layer is None:
            log.info("histogram.layer_not_found")
            raise TileNotFoundError(f"Layer {layer_id} not found")

        timing_start = perf_counter()

        start = layer.vmin * 4
        end = layer.vmax * 4
        bins = 128

        log = log.bind(start=start, end=end, bins=bins)

        edges = np.linspace(start, end, bins + 1)
        counts = np.zeros(bins)

        for tile_x in [0, 1]:
            tile, pushable = tiles.pull(
                PullableTile(
                    layer_id=layer_id,
                    x=tile_x,
                    y=0,
                    level=0,
                    # Bypass auth for this generation process
                    grants=set(layer.grant) if layer.grant is not None else None,
                )
            )

            tiles.push(pushable)

            if tile.data is not None:
                counts += np.histogram(tile.data, bins=edges)[0]

        timing_end = perf_counter()
        log = log.bind(dt=timing_end - timing_start)
        log.info("histogram.built")

        return cls(
            layer_id=layer_id,
            counts=counts,
            edges=edges,
            grant=layer.grant,
        )
