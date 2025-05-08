"""
Run a simple development server, and also creates a new database file
(temporary) that contains a sample map.
"""


def add_sample_map(text="example", width=2048, height=1024, font_size=400):
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
