"""
Histogram generation and storage.
"""

from time import perf_counter

import numpy as np
import structlog

from tilemaker.analysis.core import AnalysisProvider
from tilemaker.metadata.core import DataConfiguration
from tilemaker.providers.core import PullableTile, TileNotFoundError, Tiles
from tilemaker.settings import settings

from .products import AnalysisProduct


class HistogramProduct(AnalysisProduct):
    layer_id: str

    counts: list[int] | None = None
    edges: list[float] | None = None

    vmin: float | None = None
    vmax: float | None = None

    @property
    def hash(self):
        return f"hist-{self.layer_id}"

    def read(self, cache: AnalysisProvider, grants: set[str]):
        return cache.pull(self.hash, grants=grants, validate_type=HistogramProduct)

    def build(
        self,
        tiles: Tiles,
        metadata: DataConfiguration,
        cache: AnalysisProvider,
        grants: set[str],
    ):
        log = structlog.get_logger()

        layer_id = self.layer_id

        log = log.bind(layer_id=layer_id)

        layer = metadata.layer(layer_id=layer_id)

        if layer is None:
            log.info("histogram.layer_not_found")
            raise TileNotFoundError(f"Layer {layer_id} not found")

        timing_start = perf_counter()

        read_tiles = []

        # Retrieve only the top-level tiles for histogramming; they will either be cached
        # or need to be cached anyway.
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
            read_tiles.append(tile)

        vmin = layer.vmin
        vmax = layer.vmax

        auto_vmin = vmin == "auto"
        auto_vmax = vmax == "auto"

        if auto_vmin or auto_vmax:
            combined_array = np.hstack(
                (read_tiles[0].data.flatten(), read_tiles[1].data.flatten())
            )
            combined_array = combined_array[np.isfinite(combined_array)]
            suggested_vmin, suggested_vmax = np.quantile(
                combined_array,
                q=(
                    settings.analysis_auto_contrast_percentile,
                    1.0 - settings.analysis_auto_contrast_percentile,
                ),
                overwrite_input=True,
            )

            if auto_vmin:
                vmin = suggested_vmin
            if auto_vmax:
                vmax = suggested_vmax

        if vmin > vmax:
            temp = vmax
            vmax = vmin
            vmin = temp

        # Decide where the histogram is generated between.
        # Both have the same sign: vmin / 4 -> vmax * 4
        # Different sign: vmin * 4 -> vmax * 4

        if (vmin >= 0 and vmax >= 0) or (vmin <= 0 and vmax <= 0):
            start = vmin / 4.0
            end = vmax * 4.0
        else:
            start = vmin * 4.0
            end = vmax * 4.0

        bins = 128

        log = log.bind(start=start, end=end, bins=bins)

        log.info("histogram.binning")

        edges = np.linspace(start, end, bins + 1)
        counts = np.zeros(bins)

        for tile in read_tiles:
            if tile.data is not None:
                counts += np.histogram(tile.data, bins=edges)[0]

        timing_end = perf_counter()
        log = log.bind(dt=timing_end - timing_start)
        log.info("histogram.built")

        self.counts = counts.tolist()
        self.edges = edges.tolist()
        self.vmin = vmin
        self.vmax = vmax
        self.grant = layer.grant

        cache.push(self)

        return self
