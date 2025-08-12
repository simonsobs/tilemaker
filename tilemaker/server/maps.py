"""
Endpoints for maps.
"""

import io
from typing import Literal

from astropy.io import fits
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)

from tilemaker.metadata.definitions import MapGroup
from tilemaker.processing.extractor import extract
from tilemaker.providers.fits import PullableTile

from ..processing.renderer import Renderer, RenderOptions

renderer = Renderer(format="webp")

maps_router = APIRouter(prefix="/maps", tags=["Maps and Tiles"])


@maps_router.get(
    "",
    response_model=list[MapGroup],
    summary="Get the list of map groups.",
    description="Retrieve a list of MapGroup shaped objects, each containing a list of Maps, with a list of Bands, and finally a list of Layers.",
)
def get_maps(request: Request):
    return [x for x in request.app.config.map_groups if x.auth(request.auth.scopes)]


@maps_router.get(
    "/{layer_id}/submap/{left}/{right}/{top}/{bottom}/image.{ext}",
    summary="Generate a cut-out of the map.",
    description="Download and extract (from the base map) a rendered cut-out. Downloads at the full resolution of the underlying map with no additional filter function.",
)
def get_submap(
    layer_id: str,
    left: float,
    right: float,
    top: float,
    bottom: float,
    ext: Literal["jpg", "webp", "png", "fits"],
    request: Request,
    bt: BackgroundTasks,
    render_options: RenderOptions = Depends(RenderOptions),
    show_grid: bool = False,
):
    """
    Get a submap of the specified band.
    """

    submap, pushables = extract(
        layer_id=layer_id,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        tiles=request.app.tiles,
        grants=request.auth.scopes,
        metadata=request.app.config,
        show_grid=show_grid,
    )

    bt.add_task(request.app.tiles.push, pushables)

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
    layer: str,
    level: int,
    y: int,
    x: int,
    bt: BackgroundTasks,
    request: Request,
):
    tile, pushables = request.app.tiles.pull(
        PullableTile(layer_id=layer, x=x, y=y, level=level, grants=request.auth.scopes)
    )

    bt.add_task(request.app.tiles.push, pushables)

    return tile.data


@maps_router.get(
    "/{layer}/{level}/{y}/{x}/tile.{ext}",
    summary="Retrieve an individual tile.",
    description="Individual tiles are hosted at a layer level, with them having three axes: `level`, `y`, and `x`. We support extensions of 'png', 'webp', and 'jpg'.",
)
def get_tile(
    layer: str,
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
        layer=layer,
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
