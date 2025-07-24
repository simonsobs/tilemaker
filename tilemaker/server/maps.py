"""
Endpoints for maps.
"""

import io

import numpy as np
from astropy.io import fits
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from sqlalchemy import select
from sqlalchemy.orm import subqueryload

from tilemaker.processing.extractor import extract
from tilemaker.server.caching import (
    TileCache,
    TileNotFound,
)

from .. import database as db
from .. import orm
from ..orm.map import MapResponse
from ..processing.renderer import Renderer, RenderOptions
from .auth import allow_proprietary, filter_by_proprietary

renderer = Renderer(format="webp")

maps_router = APIRouter(prefix="/maps")


@maps_router.get("")
def get_maps(request: Request):
    with db.get_session() as session:
        stmt = filter_by_proprietary(query=select(orm.Map), request=request)
        results = session.exec(stmt).scalars().unique().all()

    return results


@maps_router.get("/{map}", response_model=MapResponse)
def get_map(map: int, request: Request):
    with db.get_session() as session:
        stmt = filter_by_proprietary(
            select(orm.Map)
            .options(subqueryload(orm.Map.bands))
            .where(orm.Map.id == map),
            request=request,
        )
        result = session.exec(stmt).unique().one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Map not found")

    return result[0]


@maps_router.get("/{map}/{band}/submap/{left}/{right}/{top}/{bottom}/image.{ext}")
def get_submap(
    map: int,
    band: int,
    left: float,
    right: float,
    top: float,
    bottom: float,
    ext: str,
    request: Request,
    render_options: RenderOptions = Depends(RenderOptions),
):
    """
    Get a submap of the specified band.
    """

    if ext not in ["jpg", "webp", "png", "fits"]:
        raise HTTPException(status_code=400, detail="Not an acceptable extension")

    submap = extract(
        band_id=band,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        proprietary=allow_proprietary(request=request),
    )

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


def core_tile_retrieval(
    db,
    cache: TileCache,
    map: int,
    band: str,
    level: int,
    y: int,
    x: int,
    bt: BackgroundTasks,
    request: Request,
):
    user_has_proprietary = allow_proprietary(request=request)

    # Check if the tile is in the cache
    try:
        public_tile_cache = cache.get_cache(
            band, x, y, level, proprietary=user_has_proprietary
        )
        return public_tile_cache
    except TileNotFound:
        pass

    with db.get_session() as session:
        stmt = select(orm.Tile).where(
            orm.Tile.band_id == int(band),
            orm.Tile.level == int(level),
            orm.Tile.y == int(y),
            orm.Tile.x == int(x),
        )

        result = session.exec(stmt).one_or_none()
        result = result[0]
        tile_size = result.band.tile_size

    if result is not None and result.data is not None:
        numpy_buf = np.frombuffer(result.data, dtype=result.data_type).reshape(
            (tile_size, tile_size)
        )
    else:
        numpy_buf = None

    # Send her back to the cache
    bt.add_task(
        cache.set_cache,
        band=int(band),
        x=int(x),
        y=int(y),
        level=int(level),
        data=numpy_buf,
        proprietary=result.proprietary,
    )

    # Critical -- otherwise non-proprietary users will get proprietary tiles
    if result.proprietary and not user_has_proprietary:
        return None

    return numpy_buf


@maps_router.get("/{map}/{band}/{level}/{y}/{x}/tile.{ext}")
def get_tile(
    map: int,
    band: str,
    level: int,
    y: int,
    x: int,
    ext: str,
    request: Request,
    bt: BackgroundTasks,
    render_options: RenderOptions = Depends(RenderOptions),
):
    """
    Grab an individual tile. This should be very fast, because we use
    a composite primary key for band, level, x, and y.

    Supported extensions:
    - jpg
    - webp
    - png

    Note: This does not support FITS tiles, as they are not
    typically used for rendering. If you need FITS images, please
    use the `/maps/{map}/{band}/submap/{left}/{right}/{top}/{bottom}/image.fits`
    endpoint instead.
    """

    if render_options.flip:
        # Flipping is really a reconfiguration of -180 < RA < 180 to 360 < RA < 0;
        # it's a card-folding operation.
        if level != 0:
            # Level of zero requires no flipping apart from at the tile level.
            midpoint = 2 ** (level)
            if x < midpoint:
                x = (2 ** (level) - 1) - x
            else:
                x = (2 ** (level) - 1) - (x - midpoint) + midpoint

    if ext not in ["jpg", "webp", "png"]:
        raise HTTPException(status_code=400, detail="Not an acceptable extension")

    numpy_buf = core_tile_retrieval(
        db=db,
        cache=request.app.cache,
        map=map,
        band=band,
        level=level,
        y=y,
        x=x,
        request=request,
        bt=bt,
    )

    if numpy_buf is None:
        raise HTTPException(status_code=404, detail="Tile not found")

    with io.BytesIO() as output:
        renderer.render(output, numpy_buf, render_options=render_options)
        return Response(content=output.getvalue(), media_type=f"image/{ext}")
