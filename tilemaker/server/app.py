"""
Main server app.
"""

import io

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import subqueryload
from sqlmodel import select

from .. import database as db
from .. import orm
from ..processing.renderer import Renderer, RenderOptions

app = FastAPI()
render_options = RenderOptions()
renderer = Renderer(format="jpg")

origins = [
    "http://localhost",
    "http://localhost:1234",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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

    if ext not in ["jpg"]:
        raise HTTPException(
            status_code=400, detail="Not an acceptable extension"
        )

    with db.get_session() as session:
        stmt = (
            select(orm.Tile).where(
                orm.Tile.band_id==band,
                orm.Tile.level==level,
                orm.Tile.y==y,
                orm.Tile.x==x,
            )
        )

        result=session.exec(stmt).one_or_none()

        # TODO: Optimize this. Maybe in-memory cache?
        tile_size = result.band.tile_size

    if result is None:
        raise HTTPException(status_code=404, detail="Tile not found")
    
    numpy_buf = np.frombuffer(result.data, dtype=np.float32).reshape((tile_size, tile_size))
    
    if ext == "jpg":
        with io.BytesIO() as output:
            renderer.render(output, numpy_buf, render_options=render_options)
            return Response(content=output.getvalue(), media_type="image/jpg")