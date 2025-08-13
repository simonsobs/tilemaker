"""
Histogram router.
"""

import io

import matplotlib.pyplot as plt
import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from tilemaker.analysis.core import ProductNotFoundError
from tilemaker.providers.core import TileNotFoundError

histogram_router = APIRouter(prefix="/histograms", tags=["Histograms"])

CMAP_CACHE = {}


class HistogramResponse(BaseModel):
    edges: list[float]
    histogram: list[int]
    layer_id: str


@histogram_router.get(
    "/{cmap}.png",
    summary="Get a 8 x 256 image of a colour map for visualisation.",
    description="Renders a PNG version of the colour bar from matplotlib for display as part of the interface.",
)
def histograms_cmap(cmap: str, request: Request):
    """"""
    try:
        data = CMAP_CACHE.get(cmap, None)

        if data is None:
            color_map = plt.get_cmap(cmap)
            mapped = color_map([np.linspace(0, 1, 256)] * 8)
            with io.BytesIO() as output:
                plt.imsave(output, mapped)
                data = output.getvalue()
                CMAP_CACHE[cmap] = data

        return Response(content=data, media_type="image/png")
    except ValueError:
        raise HTTPException(status_code=404, detail="Color map not found")


@histogram_router.get(
    "/data/{layer}",
    response_model=HistogramResponse,
    summary="Get a histogram for an individual layer.",
    description="Render a histogram at the top level of the map for the layer. Returns bin edges and counts in each bin. Note that the histogram is rendered between 4x the vmin and vmax of the recommended colour map, and uses 128 linearly spaced bins. Layer IDs can be retrieved using the maps endpoints.",
)
def histogram_data(layer: str, request: Request) -> HistogramResponse:
    analysis_id = f"hist-{layer}"

    try:
        resp = request.app.analyses.pull(analysis_id, grants=request.auth.scopes)
    except (TileNotFoundError, ProductNotFoundError):
        raise HTTPException(status_code=404, detail="Histogram not found")

    return HistogramResponse(
        edges=resp.edges, histogram=resp.counts, layer_id=resp.layer_id
    )
