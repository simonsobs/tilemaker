"""
Endpoint to search map groups and its children
"""

from fastapi import (
    APIRouter,
    Query,
    Request,
)

from tilemaker.metadata.definitions import SearchResponse

search_router = APIRouter(prefix="/search", tags=["Search map groups"])


@search_router.get("", response_model=SearchResponse)
def search_layers(request: Request, q: str = Query(..., min_length=1)):
    authorized_groups = [
        g.dict() for g in request.app.config.map_groups if g.auth(request.auth.scopes)
    ]
    result = request.app.config.filter_map_groups(authorized_groups, q)
    return SearchResponse(
        filtered_layer_menu=result.filtered_layer_menu,
        matched_ids=result.matched_ids,
    )
