"""
Histogram router.
"""

from astropy.coordinates import SkyCoord
from astropy.units import Quantity
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError

from tilemaker.analysis.aperture import ApertureInformation
from tilemaker.analysis.core import ProductNotFoundError
from tilemaker.providers.core import TileNotFoundError

analysis_router = APIRouter(prefix="/analysis", tags=["Analysis"])

CMAP_CACHE = {}


class ApertureResponse(BaseModel):
    layer_id: str
    ra: float
    dec: float
    radius: float
    mean: float | None = None
    std: float | None = None
    max: float | None = None
    min: float | None = None


@analysis_router.get(
    "/aperture/{layer}",
    response_model=ApertureResponse,
    summary="Get aperture information for a given layer",
    description=(
        "Calculate cumulative statistics for an aperture on the sky for a given layer. "
        "Returns mean, standard deviation, min and max values within the aperture. "
        "The aperture is defined by a central RA and Dec (in degrees) and a radius "
        "(in arcminutes)."
    ),
)
def aperture_data(
    layer: str, ra: float, dec: float, radius: float, request: Request
) -> ApertureResponse:
    try:
        data = ApertureInformation(
            layer_id=layer,
            position=SkyCoord(ra=ra, dec=dec, unit="deg"),
            radius=Quantity(radius, "arcmin"),
            grant=None,
        )
    except (TypeError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {e}")

    try:
        resp = data.build(
            tiles=request.app.analyses.tiles,
            metadata=request.app.analyses.metadata,
            cache=request.app.analyses,
            grants=request.auth.scopes,
        )
    except (TileNotFoundError, ProductNotFoundError):
        raise HTTPException(status_code=404, detail="Histogram not found")

    return ApertureResponse(
        layer_id=resp.layer_id,
        ra=resp.position.ra.to_value("deg"),
        dec=resp.position.dec.to_value("deg"),
        radius=resp.radius.to_value("arcmin"),
        mean=resp.mean,
        std=resp.std,
        max=resp.max,
        min=resp.min,
    )
