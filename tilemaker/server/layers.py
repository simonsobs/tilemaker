"""
Endpoint for layer and tile data
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

from tilemaker.metadata.definitions import (
    BandMenuState,
    LayerDefault,
    LayerSummary,
    LayerWithMenuState,
    MapGroupMenuState,
    MapMenuState,
)
from tilemaker.processing.extractor import extract
from tilemaker.providers.fits import PullableTile

from ..processing.renderer import Renderer, RenderOptions

renderer = Renderer(format="webp")

layers_router = APIRouter(prefix="/layers", tags=["Layers and Tiles"])


"""
    Sets default layer to the first layer found after filtering for auth status, i.e.
    auth_map_groups[0].maps[0].bands[0].layers[0]. Also creates a menu state for the
    client to render an initial layer menu.
"""


@layers_router.get(
    "/default",
    response_model=LayerDefault,
    summary="Get the hierarchy and layer data for a default layer.",
    description="Gets layer data needed for the menu and map when first loaded.",
)
def get_default_layer(request: Request):
    authorized_map_groups = list(
        filter(lambda x: x.auth(request.auth.scopes), request.app.config.map_groups)
    )

    # Return early because we have no default layer nor menu state
    if not authorized_map_groups:
        return LayerDefault(
            layer=None,
            default_layer_menu=[],
        )

    # Otherwise, set defaults to first index at each level
    default_map_group = authorized_map_groups[0]
    default_map = default_map_group.maps[0]
    default_band = default_map.bands[0]
    default_layer = LayerWithMenuState(
        **default_band.layers[0].model_dump(),
        map_group_id=default_map_group.map_group_id,
        map_id=default_map.map_id,
        band_id=default_band.band_id,
    )

    # Make layer summaries for all the default band's layers
    default_layer_summaries = [
        LayerSummary(
            layer_id=layer.layer_id, name=layer.name, description=layer.description
        )
        for layer in default_band.layers
    ]

    # Add the default_layer_summaries only to the default band; otherwise, assign an empty list
    default_band_summaries = []
    for band in default_map.bands:
        default_band_summaries.append(
            BandMenuState(
                band_id=band.band_id,
                name=band.name,
                description=band.description,
                layers=default_layer_summaries
                if band.band_id == default_band.band_id
                else [],
            )
        )

    # Add the default_band_summaries only to the default map; otherwise, assign an empty list
    default_map_summaries = []
    for map in default_map_group.maps:
        default_map_summaries.append(
            MapMenuState(
                map_id=map.map_id,
                name=map.name,
                description=map.description,
                bands=default_band_summaries
                if map.map_id == default_map.map_id
                else [],
            )
        )

    # Add the default_map_summaries only to the default map group; otherwise, assign an empty list
    default_map_groups = []
    for map_group in authorized_map_groups:
        default_map_groups.append(
            MapGroupMenuState(
                map_group_id=map_group.map_group_id,
                name=map_group.name,
                description=map_group.description,
                maps=default_map_summaries
                if map_group.map_group_id == default_map_group.map_group_id
                else [],
            )
        )

    return LayerDefault(
        layer=default_layer,
        default_layer_menu=default_map_groups,
    )


@layers_router.get(
    "/{layer_id}",
    response_model=LayerWithMenuState,
    summary="Get the Layer data.",
    description="Retrieve the Layer data to be rendered in the mapping client.",
)
def get_layer_with_menu_state(layer_id: str, request: Request):
    for map_group in request.app.config.map_groups:
        if map_group.auth(request.auth.scopes):
            for map in map_group.maps:
                for band in map.bands:
                    for layer in band.layers:
                        if layer.layer_id == layer_id and map_group.auth(
                            request.auth.scopes
                        ):
                            return LayerWithMenuState(
                                **layer.model_dump(),
                                map_group_id=map_group.map_group_id,
                                map_id=map.map_id,
                                band_id=band.band_id,
                            )


@layers_router.get(
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
    layer_id: str,
    level: int,
    y: int,
    x: int,
    bt: BackgroundTasks,
    request: Request,
):
    tile, pushables = request.app.tiles.pull(
        PullableTile(
            layer_id=layer_id, x=x, y=y, level=level, grants=request.auth.scopes
        )
    )

    bt.add_task(request.app.tiles.push, pushables)

    return tile.data


@layers_router.get(
    "/{layer_id}/{level}/{y}/{x}/tile.{ext}",
    summary="Retrieve an individual tile.",
    description="Individual tiles are hosted at a layer level, with them having three axes: `level`, `y`, and `x`. We support extensions of 'png', 'webp', and 'jpg'.",
)
def get_tile(
    layer_id: str,
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
        layer_id=layer_id,
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
