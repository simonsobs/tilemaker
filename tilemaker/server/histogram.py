"""
Histogram router.
"""

import io

import matplotlib.pyplot as plt
import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from .. import database as db
from .. import orm
from .auth import filter_by_proprietary

histogram_router = APIRouter(prefix="/histograms")


class HistogramResponse(BaseModel):
    edges: list[float]
    histogram: list[int]
    band_id: int


@histogram_router.get("/{cmap}.png")
def histograms_cmap(cmap: str, request: Request):
    "Get a 8 x 256 image of a colour map for visualisation."
    try:
        color_map = plt.get_cmap(cmap)
        mapped = color_map([np.linspace(0, 1, 256)] * 8)

        with io.BytesIO() as output:
            plt.imsave(output, mapped)
            return Response(content=output.getvalue(), media_type="image/png")
    except ValueError:
        raise HTTPException(status_code=404, detail="Color map not found")


@histogram_router.get("/data/{band_id}")
def histogram_data(band_id: int, request: Request) -> HistogramResponse:
    with db.get_session() as session:
        stmt = filter_by_proprietary(
            select(orm.Histogram).where(orm.Histogram.band_id == int(band_id)),
            request=request,
        )
        result = session.exec(stmt).one_or_none()

        if result is None:
            raise HTTPException(status_code=404, detail="Histogram not found")

        result = result[0]

        response = HistogramResponse(
            edges=np.frombuffer(result.edges, dtype=result.edges_data_type).tolist(),
            histogram=np.frombuffer(
                result.histogram, dtype=result.histogram_data_type
            ).tolist(),
            band_id=result.band_id,
        )

    return response
