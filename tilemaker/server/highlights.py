"""
Endpoints for highlights
"""

from fastapi import APIRouter, Request

from tilemaker.metadata.boxes import Box

highlights_router = APIRouter(prefix="/highlights", tags=["Highlights"])


@highlights_router.get(
    "/boxes", summary="Get the list of highlight boxes.", response_model=list[Box]
)
def get_highlight_boxes(request: Request):
    return [
        x
        for x in request.app.config.boxes
        if not (x.grant is not None and x.grant not in request.auth.scopes)
    ]
