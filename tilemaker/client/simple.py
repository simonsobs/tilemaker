"""
Run a simple development server, and also creates a
(temporary) file that contains a sample map.
"""


def create_sample_metadata(filename: str):
    from tilemaker.metadata.definitions import (
        Band,
        FITSLayerProvider,
        Layer,
        Map,
        MapGroup,
    )

    return [
        MapGroup(
            name="Map Group",
            description="Example",
            maps=[
                Map(
                    map_id="example",
                    name="Map",
                    description="Example",
                    bands=[
                        Band(
                            band_id="example",
                            name="Band",
                            description="Example",
                            layers=[
                                Layer(
                                    layer_id="example",
                                    name="Layer",
                                    description="Example",
                                    provider=FITSLayerProvider(
                                        filename=filename,
                                    ),
                                    units="uK",
                                    vmin=-127.0,
                                    vmax=127.0,
                                    cmap="RdBu_r",
                                )
                            ],
                        )
                    ],
                )
            ],
        )
    ]


def add_sample_map(text="example", width=4096, height=2048, font_size=800):
    """
    Creates a sample map that just says 'example'.
    """

    import os

    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from pixell import enmap, utils

    filename = "example.fits"

    if os.path.exists(filename):
        return create_sample_metadata(filename)

    # Create a blank white image (mode "L" for 8-bit pixels, black and white)
    image = Image.new("L", (width, height), color=127)

    # Create a drawing context
    draw = ImageDraw.Draw(image)

    # Load a font
    font = ImageFont.load_default(size=font_size)

    # Calculate text size and position
    x = (width) // 2
    y = (height) // 2

    # Draw the text with outline
    draw.text(
        (x, y),
        text,
        fill=0,
        font=font,
        anchor="mm",
        stroke_fill=255,
        stroke_width=font_size * 0.02,
    )

    image = ImageOps.flip(image)

    # Convert image to numpy array
    array = np.array(image, dtype=np.float32) - 127
    box = np.array([[-90, 0], [90, 360]]) * utils.degree
    res = 360 * utils.degree / width
    shape, wcs = enmap.geometry(pos=box, res=res, proj="car")

    enmap.write_fits(filename, enmap.enmap(array, wcs=wcs), extra={"BUNIT": "uK"})

    return create_sample_metadata(filename)


def add_sample_source_list(number: int = 4):
    """
    Creates a sample source list with the given number of sources.
    """

    from tilemaker.metadata.sources import Source, SourceGroup

    sources = []

    for i in range(number):
        for j in range(number):
            source_name = f"Source ({i}, {j})"

            sources.append(
                Source(
                    ra=360 * (i + 0.5) / number - 180.0,
                    dec=180 * (j + 0.5) / number - 90.0,
                    name=source_name,
                    extra=dict(
                        flux=float(i * j),
                        snr=2.1,
                    ),
                )
            )

    return [
        SourceGroup(
            source_group_id="example",
            name="Source Group",
            description="Example",
            sources=sources,
        )
    ]


def add_sample_box():
    """
    Creates a sample box.
    """

    from tilemaker.metadata.boxes import Box

    box = Box(
        top_left_ra=-10.0,
        top_left_dec=10.0,
        bottom_right_ra=10.0,
        bottom_right_dec=-10.0,
        name="Example Box",
        description="An example highlight box.",
    )

    return [box]
