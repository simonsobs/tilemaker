"""
Main server app.
"""

import io

from fastapi.templating import Jinja2Templates
import matplotlib.pyplot as plt
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import subqueryload
from sqlmodel import select

from .. import database as db
from .. import orm
from ..processing.renderer import Renderer, RenderOptions
from ..settings import settings

app = FastAPI()
render_options = RenderOptions()
renderer = Renderer(format="webp")

if settings.add_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Make a simple static dude
if settings.static_directory is not None:
    app.mount("/static", StaticFiles(directory=settings.static_directory), name="spa")
    
    templates = Jinja2Templates(directory="templates")

    @app.get("/")
    async def home(request: Request):
        response = templates.TemplateResponse(
            "index.html", context={"settings": settings, "request": request}
        )
        return response

@app.get("/maps")
def get_maps():
    with db.get_session() as session:
        stmt = select(orm.Map)
        results = session.exec(stmt).all()

    return results


@app.get("/maps/{map}", response_model=orm.map.MapResponse)
def get_map(map: str):
    with db.get_session() as session:
        stmt = (
            select(orm.Map).options(subqueryload(orm.Map.bands))
            .where(orm.Map.name == map)
        )
        result = session.exec(stmt).one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Map not found")
    
    return result


@app.get("/maps/{map}/{band}/{level}/{y}/{x}/tile.{ext}")
def get_tile(
    map: str,
    band: str,
    level: int,
    y: int,
    x: int,
    ext: str,
    render_options: RenderOptions = Depends(RenderOptions)
):
    """
    Grab an individual tile. This should be very fast, because we use
    a composite primary key for band, level, x, and y.

    Supported extensions:
    # - .raw (you will get the raw array data)
    - .jpg (you will get a rendered JPG)
    """

    if ext not in ["jpg", "webp", "png"]:
        raise HTTPException(
            status_code=400, detail="Not an acceptable extension"
        )

    with db.get_session() as session:
        stmt = (
            select(orm.Tile).where(
                orm.Tile.band_id==int(band),
                orm.Tile.level==int(level),
                orm.Tile.y==int(y),
                orm.Tile.x==int(x),
            )
        )

        result=session.exec(stmt).one_or_none()

        # TODO: Optimize this. Maybe in-memory cache?
        tile_size = result.band.tile_size

    if result is None:
        raise HTTPException(status_code=404, detail="Tile not found")
    
    numpy_buf = np.frombuffer(result.data, dtype=result.data_type).reshape((tile_size, tile_size))
    
    if ext == "jpg":
        with io.BytesIO() as output:
            renderer.render(output, numpy_buf, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/jpg")
    elif ext == "webp":
        with io.BytesIO() as output:
            renderer.render(output, numpy_buf, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/webp")
    elif ext == "png":
        with io.BytesIO() as output:
            renderer.render(output, numpy_buf, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/png")
        

@app.get("/histograms/{cmap}.png")
def histograms_cmap(
    cmap: str
):
    "Get a 8 x 256 image of a colour map for visualisation."
    try:
        color_map = plt.get_cmap(cmap)
        mapped = color_map([np.linspace(0, 1, 256)] * 8)

        with io.BytesIO() as output:
            plt.imsave(output, mapped)
            return Response(content=output.getvalue(), media_type="image/png")
    except ValueError:
        raise HTTPException(status_code=404, detail="Color map not found")
    
class HistogramResponse(BaseModel):
    edges: list[float]
    histogram: list[int]
    band_id: int
    
@app.get("/histograms/data/{band_id}")
def histogram_data(
    band_id: int
) -> HistogramResponse:
    with db.get_session() as session:
        stmt = select(orm.Histogram).where(orm.Histogram.band_id == int(band_id))
        result = session.exec(stmt).one_or_none()

        if result is None:
            raise HTTPException(status_code=404, detail="Histogram not found")
        
        response = HistogramResponse(
            edges=np.frombuffer(result.edges, dtype=result.edges_data_type).tolist(),
            histogram=np.frombuffer(result.histogram, dtype=result.histogram_data_type).tolist(),
            band_id=result.band_id
        )

    return response