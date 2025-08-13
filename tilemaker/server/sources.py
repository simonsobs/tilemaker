"""
Sources router
"""

from fastapi import APIRouter, HTTPException, Request

from tilemaker.metadata.sources import SourceGroup, SourceGroupStub

sources_router = APIRouter(prefix="/sources", tags=["Sources"])


@sources_router.get(
    "",
    response_model=list[SourceGroupStub],
    summary="Get the available source groups.",
    description="Get the full list of available 'source groups'. A source group is a list of associated sources (e.g. an individual catalog). Note that the source information itself is not included here; see /{id}.",
)
def get_sources(request: Request):
    return [
        x
        for x in request.app.config.source_groups
        if not (x.grant is not None and x.grant not in request.auth.scopes)
    ]


@sources_router.get(
    "/{id}",
    response_model=SourceGroup,
    response_model_exclude=["provider", "grant"],
    summary="Get the full detail of a source group.",
    description="Gets all of the source data for a specific source group.",
)
def get_source_list(id: str, request: Request):
    x = request.app.config.source_group(source_group_id=id)

    if x is None or (x.grant is not None and x.grant not in request.auth.scopes):
        raise HTTPException(404, f"Source group {id} not found")

    return x
