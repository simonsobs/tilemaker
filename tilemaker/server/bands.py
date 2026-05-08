"""
Endpoint for summary data of a band's layers
"""

from fastapi import (
    APIRouter,
    Request,
)

from tilemaker.metadata.definitions import LayerSummary

bands_router = APIRouter(prefix="/bands", tags=["List of Bands"])


@bands_router.get(
    "/{band_id}/layers",
    response_model=list[LayerSummary],
    summary="Get the list of layer summaries associated with a Band.",
    description="Retrieve a list of LayerSummary objects that belong to a particular Band.",
)
def get_layer_summaries_of_band(band_id: str, request: Request):
    layer_summaries = []
    for band in request.app.config.bands:
        if band.band_id == band_id and band.auth(request.auth.scopes):
            for layer in band.layers:
                layer_summary = LayerSummary(
                    layer_id=layer.layer_id,
                    name=layer.name,
                    description=layer.description,
                )
                layer_summaries.append(layer_summary)
    return layer_summaries
