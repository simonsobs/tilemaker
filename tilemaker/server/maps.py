"""
Endpoints for maps.
"""

import io
from typing import Literal

from fastapi import (
    APIRouter,
    Request
)

from tilemaker.metadata.definitions import BandBase

maps_router = APIRouter(prefix="/maps", tags=["Maps and Tiles"])


@maps_router.get(
    "/{map_id}/bands",
    response_model=list[BandBase],
    summary="Get the list of band summaries associated with a Map.",
    description="Retrieve a list of BandSummary objects that belong to a particular Map."
)
def get_layer_summaries_of_band(
    map_id: str,
    request: Request
):
    for map_group in request.app.config.map_groups:
        for map in map_group.maps:
            if (map.map_id == map_id and map_group.auth(request.auth.scopes)):
                for band in map.bands:
                    band_summaries = []
                    band_summary = BandBase(
                        band_id=band.band_id,
                        name=band.name,
                        description=band.description,
                    )
                    band_summaries.append(band_summary)
                return band_summaries
    return []