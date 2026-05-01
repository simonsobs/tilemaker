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
    raw_groups = [
        g.dict() for g in request.app.config.map_groups if g.auth(request.auth.scopes)
    ]
    result = filter_map_groups(raw_groups, q)

    return SearchResponse(
        filtered_layer_menu=result["filtered_map_groups"],
        matched_ids=list(result["matched_ids"]),
    )


def match(name: str, query: str) -> bool:
    """Case-insensitive substring match — swap in rapidfuzz here later if needed."""
    return query.lower() in name.lower()


def filter_map_groups(map_groups: list, query: str) -> dict:
    matched_ids: set[str] = set()
    filtered_groups = []

    for group in map_groups:
        # Group name matches — keep entire subtree intact
        if match(group["name"], query):
            matched_ids.add(group["map_group_id"])
            filtered_groups.append(group)
            continue

        filtered_maps = []
        for map in group.get("maps", []):
            # Map name matches — keep entire subtree intact
            if match(map["name"], query):
                matched_ids.add(map["map_id"])
                filtered_maps.append(map)
                continue

            filtered_bands = []
            for band in map.get("bands", []):
                # Band name matches — keep entire subtree intact
                if match(band["name"], query):
                    matched_ids.add(band["band_id"])
                    filtered_bands.append(band)
                    continue

                filtered_layers = [
                    layer
                    for layer in band.get("layers", [])
                    if match(layer["name"], query)
                    and matched_ids.add(layer["layer_id"]) is None
                ]
                if filtered_layers:
                    filtered_bands.append({**band, "layers": filtered_layers})

            if filtered_bands:
                filtered_maps.append({**map, "bands": filtered_bands})

        if filtered_maps:
            filtered_groups.append({**group, "maps": filtered_maps})

    return {"filtered_map_groups": filtered_groups, "matched_ids": matched_ids}
