"""
Endpoints for getting list of map group summaries and a list of a map group's map summaries.
"""

from fastapi import (
    APIRouter,
    Request,
)

from tilemaker.metadata.definitions import MapBase, MapGroupBase

map_groups_router = APIRouter(prefix="/map-groups", tags=["List of Map Groups"])


@map_groups_router.get(
    "",
    response_model=list[MapGroupBase],
    summary="Get the list of map group summaries.",
    description="Retrieve a list of MapGroupSummary objects.",
)
def get_map_group_summaries(request: Request):
    map_group_summaries = []
    for x in request.app.config.map_groups:
        if x.auth(request.auth.scopes):
            map_group_summary = MapGroupBase(
                map_group_id=x.map_group_id,
                name=x.name,
                description=x.description,
            )
            map_group_summaries.append(map_group_summary)

    return map_group_summaries


@map_groups_router.get(
    "/{map_group_id}/maps",
    response_model=list[MapBase],
    summary="Get the list of map summaries associated with a Map Group.",
    description="Retrieve a list of MapSummary objects that belong to a particular Map Group.",
)
def get_map_summaries_of_map_group(map_group_id: str, request: Request):
    map_summaries = []
    for map_group in request.app.config.map_groups:
        if map_group.map_group_id == map_group_id and map_group.auth(
            request.auth.scopes
        ):
            for map in map_group.maps:
                map_summary = MapBase(
                    map_id=map.map_id,
                    name=map.name,
                    description=map.description,
                )
                map_summaries.append(map_summary)
    return map_summaries
