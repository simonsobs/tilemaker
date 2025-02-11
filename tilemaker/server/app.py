"""
Main server app.
"""

import io
from collections.abc import AsyncIterator
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi_cache.coder import PickleCoder
from pydantic import BaseModel
from sqlalchemy.orm import subqueryload
from sqlmodel import select

from tilemaker.processing.extractor import extract

from .. import database as db
from .. import orm
from ..processing.renderer import Renderer, RenderOptions
from ..settings import settings

if settings.use_in_memory_cache:
    from fastapi_cache import FastAPICache
    from fastapi_cache.decorator import cache

    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        FastAPICache.init(backend="in-memory")
        yield
else:
    lifespan = None

    def cache(func, coder=None, expire=None):
        return func


app = FastAPI(lifespan=lifespan)
render_options = RenderOptions()
renderer = Renderer(format="webp")
STATIC_DIRECTORY = Path(__file__).parent / "static"

if settings.add_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )



@app.get("/maps")
def get_maps():
    with db.get_session() as session:
        stmt = select(orm.Map)
        results = session.exec(stmt).all()

    return results


@app.get("/maps/{map}", response_model=orm.map.MapResponse)
def get_map(map: int):
    with db.get_session() as session:
        stmt = (
            select(orm.Map)
            .options(subqueryload(orm.Map.bands))
            .where(orm.Map.id == map)
        )
        result = session.exec(stmt).one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Map not found")

    return result


@app.get("/highlights/boxes")
def get_highlight_boxes():
    with db.get_session() as session:
        stmt = select(orm.HighlightBox)
        results = session.exec(stmt).all()

    return results


@app.put("/highlights/boxes/new")
def add_highlight_box(
    top_left: tuple[float, float],
    bottom_right: tuple[float, float],
    description: str | None,
    name: str | None,
):
    """
    Add a new highlight box. For conversion from selection regions.
    """
    with db.get_session() as session:
        new_box = orm.HighlightBox(
            top_left_ra=top_left[0],
            top_left_dec=top_left[1],
            bottom_right_ra=bottom_right[0],
            bottom_right_dec=bottom_right[1],
            description=description,
            name=name,
        )
        session.add(new_box)
        session.commit()
        new_id = new_box.id

    return new_id


@app.delete("/highlights/boxes/{id}")
def delete_highlight_box(id: int):
    with db.get_session() as session:
        stmt = select(orm.HighlightBox).where(orm.HighlightBox.id == id)
        result = session.exec(stmt).one_or_none()

        if result is None:
            raise HTTPException(status_code=404, detail="Box not found")

        session.delete(result)
        session.commit()

    return


@app.get("/maps/{map}/{band}/submap/{left}/{right}/{top}/{bottom}/image.{ext}")
def get_submap(
    map: int,
    band: int,
    left: float,
    right: float,
    top: float,
    bottom: float,
    ext: str,
    render_options: RenderOptions = Depends(RenderOptions),
):
    """
    Get a submap of the specified band.
    """

    if ext not in ["jpg", "webp", "png", "fits"]:
        raise HTTPException(status_code=400, detail="Not an acceptable extension")

    submap = extract(band_id=band, left=left, right=right, top=top, bottom=bottom)

    if ext == "jpg":
        with io.BytesIO() as output:
            renderer.render(output, submap, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/jpg")
    elif ext == "webp":
        with io.BytesIO() as output:
            renderer.render(output, submap, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/webp")
    elif ext == "png":
        with io.BytesIO() as output:
            renderer.render(output, submap, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/png")
    elif ext == "fits":
        with io.BytesIO() as output:
            hdu = fits.PrimaryHDU(submap)
            hdu.writeto(output)
            return Response(content=output.getvalue(), media_type="image/fits")


@app.get("/maps/{map}/{band}/{level}/{y}/{x}/tile.{ext}")
@cache(expire=3600, coder=PickleCoder)
def get_tile(
    map: int,
    band: str,
    level: int,
    y: int,
    x: int,
    ext: str,
    render_options: RenderOptions = Depends(RenderOptions),
):
    """
    Grab an individual tile. This should be very fast, because we use
    a composite primary key for band, level, x, and y.

    Supported extensions:
    # - .raw (you will get the raw array data)
    - .jpg (you will get a rendered JPG)
    """

    if ext not in ["jpg", "webp", "png"]:
        raise HTTPException(status_code=400, detail="Not an acceptable extension")

    with db.get_session() as session:
        stmt = select(orm.Tile).where(
            orm.Tile.band_id == int(band),
            orm.Tile.level == int(level),
            orm.Tile.y == int(y),
            orm.Tile.x == int(x),
        )

        result = session.exec(stmt).one_or_none()

        # TODO: Optimize this. Maybe in-memory cache?
        tile_size = result.band.tile_size

    if result is None or result.data is None:
        raise HTTPException(status_code=404, detail="Tile not found")

    numpy_buf = np.frombuffer(result.data, dtype=result.data_type).reshape(
        (tile_size, tile_size)
    )

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
def histograms_cmap(cmap: str):
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
def histogram_data(band_id: int) -> HistogramResponse:
    with db.get_session() as session:
        stmt = select(orm.Histogram).where(orm.Histogram.band_id == int(band_id))
        result = session.exec(stmt).one_or_none()

        if result is None:
            raise HTTPException(status_code=404, detail="Histogram not found")

        response = HistogramResponse(
            edges=np.frombuffer(result.edges, dtype=result.edges_data_type).tolist(),
            histogram=np.frombuffer(
                result.histogram, dtype=result.histogram_data_type
            ).tolist(),
            band_id=result.band_id,
        )

    return response


@app.get("/sources")
def get_sources():
    with db.get_session() as session:
        stmt = select(orm.SourceList)
        results = session.exec(stmt).all()

    return results


@app.get("/sources/{id}")
def get_source_list(id: int):
    with db.get_session() as session:
        stmt = select(orm.SourceItem).where(orm.SourceItem.source_list_id == id)
        result = session.exec(stmt).all()

    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")

    return result


if settings.serve_frontend:
    # The index.html is actually in static. But if anyone wants to access it
    # they might go to /, /index.html, /index.htm... etc. So we need to have a
    # catch-all route for static content
    @app.get("/")
    async def serve_spa():
        index_file_path = STATIC_DIRECTORY / "index.html"
        return FileResponse(index_file_path)

# Mount the built-in client.
if settings.serve_frontend:
    app.mount("/", StaticFiles(directory=STATIC_DIRECTORY), name="spa")
