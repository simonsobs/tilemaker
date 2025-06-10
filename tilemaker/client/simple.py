"""
Run a simple development server, and also creates a new database file
(temporary) that contains a sample map.
"""


def add_sample_map(text="example", width=4096, height=2048, font_size=800):
    """
    Creates a sample map that just says 'example'.
    """

    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from sqlalchemy import select

    import tilemaker.database as db
    import tilemaker.orm
    from tilemaker.processing.simple import SimpleMapMaker

    db.create_database_and_tables()
    map_name = "Example"
    description = "An example simple map taht you will use for debugging only!"

    with db.get_session() as session:
        results = (
            session.exec(select(tilemaker.orm.Map).filter_by(name=map_name))
            .unique()
            .scalars()
            .all()
        )

        if results:
            return

    # Create a blank white image (mode "L" for 8-bit pixels, black and white)
    image = Image.new("L", (width, height), color=255)

    # Create a drawing context
    draw = ImageDraw.Draw(image)

    # Load a font
    font = ImageFont.load_default(size=font_size)

    # Calculate text size and position
    x = (width) // 2
    y = (height) // 2

    # Draw the text in black (0)
    draw.text((x, y), text, fill=0, font=font, anchor="mm")

    image = ImageOps.flip(image)

    # Convert image to numpy array
    array = np.array(image).T

    map_maker = SimpleMapMaker(raw_array=array)
    tiles = map_maker.make_tiles()

    with db.get_session() as session:
        map_metadata = tilemaker.orm.Map(name=map_name, description=description)

        band = tilemaker.orm.Band(
            map=map_metadata,
            map_name=map_name,
            tiles_available=True,
            levels=max(tiles.keys()),
            tile_size=map_maker.tile_size,
            units="None",
            quantity="Floats",
            recommended_cmap="viridis",
            recommended_cmap_max=255.0,
            recommended_cmap_min=0.0,
            bounding_left=-180,
            bounding_right=180,
            bounding_bottom=-90,
            bounding_top=90,
        )

        H, edges = np.histogram(array.flat)

        histogram = tilemaker.orm.Histogram(
            band=band,
            start=-10,
            end=138,
            bins=32,
            edges_data_type=str(edges.dtype),
            edges=edges.tobytes(order="C"),
            histogram_data_type=str(H.dtype),
            histogram=H.tobytes(order="C"),
        )

        tile_metadata = []

        for depth, tile_collection in tiles.items():
            for tile_name, tile_data in tile_collection.items():
                x, y = (int(x) for x in tile_name.split("_"))
                tile_metadata.append(
                    tilemaker.orm.Tile(
                        level=depth,
                        x=x,
                        y=y,
                        band=band,
                        data=tile_data.tobytes("C"),
                        data_type=str(tile_data.dtype)
                        if tile_data is not None
                        else None,
                    )
                )

        session.add_all([map_metadata, band, histogram] + tile_metadata)
        session.commit()

    return


def add_sample_source_list(number: int = 4):
    """
    Creates a sample source list with the given number of sources.
    """

    from sqlalchemy import select

    import tilemaker.database as db
    import tilemaker.orm

    source_list_name = "Sample Source List"

    db.create_database_and_tables()

    with db.get_session() as session:
        results = (
            session.exec(
                select(tilemaker.orm.SourceList).filter_by(name=source_list_name)
            )
            .unique()
            .scalars()
            .all()
        )

    if results:
        return

    with db.get_session() as session:
        sources = []

        for i in range(number):
            for j in range(number):
                source_name = f"Source ({i}, {j})"

                sources.append(
                    tilemaker.orm.SourceItem(
                        flux=float(i * j),
                        ra=360 * (i + 0.5) / number - 180.0,
                        dec=180 * (j + 0.5) / number - 90.0,
                        name=source_name,
                    )
                )

        source_list = tilemaker.orm.SourceList(
            sources=sources,
            name=source_list_name,
            description="A sample source list with multiple sources.",
            proprietary=False,
        )

        session.add_all([source_list] + sources)
        session.commit()

    return


def add_sample_box():
    """
    Creates a sample box.
    """

    box_name = "Example Box"

    from sqlalchemy import select

    import tilemaker.database as db
    import tilemaker.orm

    with db.get_session() as session:
        result = (
            session.exec(select(tilemaker.orm.HighlightBox).filter_by(name=box_name))
            .unique()
            .scalars()
            .all()
        )

    if result:
        return

    with db.get_session() as session:
        box = tilemaker.orm.HighlightBox(
            top_left_ra=-10.0,
            top_left_dec=10.0,
            bottom_right_ra=10.0,
            bottom_right_dec=-10.0,
            name=box_name,
            description="An example highlight box.",
        )

        session.add(box)
        session.commit()

    return
