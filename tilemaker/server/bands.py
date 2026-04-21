"""
Endpoint for summary data of a band's layers
"""

from tilemaker.metadata.definitions import BandSummary, LayerSummary

from fastapi import (
    APIRouter,
    Request,
)

bands_router = APIRouter(prefix="/bands", tags=["List of Bands"])


@bands_router.get(
    "/{band_id}/layers",
    response_model=list[LayerSummary],
    summary="Get the list of layer summaries associated with a Band.",
    description="Retrieve a list of LayerSummary objects that belong to a particular Band."
)
def get_layer_summaries_of_band(
    band_id: str,
    request: Request
):
    for map_group in request.app.config.map_groups:
        for map in map_group.maps:
            for band in map.bands:
                if (band.band_id == band_id and map_group.auth(request.auth.scopes)):
                    layer_summaries = []
                    for layer in band.layers:
                        layer_summary = LayerSummary(
                            layer_id=layer.layer_id,
                            name=layer.name,
                            description=layer.description,
                        )
                        layer_summaries.append(layer_summary)
                    return layer_summaries
    return []