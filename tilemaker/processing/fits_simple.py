"""
It should in princple be possible to just use the wcs to bisect the grid.
"""

import math
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import numpy as np
from astropy import units
from astropy.io import fits
from astropy.wcs import WCS
from pixell import enmap
from pydantic import BaseModel


class StokesParameters(Enum):
    I = 0
    Q = 1
    U = 2


class FITSFile(BaseModel):
    """
    A FITS file that can link out to multiple underlying
    'bands', notably different Stokes parameters.
    """

    filename: Path
    "The filename of the FITS file."
    log_scale_data: bool = False
    "Whether or not to log scale the data."

    @property
    def individual_trees(self) -> list["FITSSimpleLoader"]:
        """
        Return a list of FITSImage objects for each 'band' in the FITS file.
        """

        # There are a number of ways that we can have a different band:
        # different HDUs, and a different STOKES parameter.

        hdus = []
        with fits.open(self.filename) as handle:
            for i, hdu in enumerate(handle):
                if "CTYPE3" in hdu.header:
                    if hdu.header["CTYPE3"] != "STOKES":
                        raise ValueError(
                            f"Unknown CTYPE3 {hdu.header['CTYPE3']} in HDU {i}."
                        )
                    else:
                        for stokes in StokesParameters:
                            hdus.append((i, stokes.name))
                        continue
                else:
                    if "NAXIS3" in hdu.header:
                        # Hmm, this is a bit of a problem. Just assume it's stokes?
                        hdu.header["CTYPE3"] = "STOKES"
                        hdu.header["CDELT3"] = 1.0
                        for stokes in StokesParameters:
                            hdus.append((i, stokes.name))
                        continue

                    hdus.append((i, None))

        return [
            FITSSimpleLoader(
                self.filename,
                hdu=i,
                identifier=stokes,
                log_scale_data=self.log_scale_data,
            )
            for i, stokes in hdus
        ]


class FITSSimpleLoader:
    filename: Path
    hdu: int
    identifier: Optional[Union[str, int]] = None
    log_scale_data: bool = False

    header: fits.header.Header
    wcs: WCS

    _map: enmap = None

    _tile_size: Optional[int] = None
    "Size of the tiles to read from the file."
    _number_of_levels: Optional[int] = None

    def __init__(
        self,
        filename: Path,
        hdu: int = 0,
        identifier: str = "Q",
        log_scale_data: bool = False,
    ):
        self.filename = Path(filename)
        self.hdu = hdu
        self.identifier = identifier
        self.log_scale_data = log_scale_data

        with fits.open(self.filename) as handle:
            self.header = handle[hdu].header
            self.wcs = WCS(self.header)

    def read_data(self) -> np.ndarray:
        """
        Read the data array for the file given the identifier.

        Returns
        -------
        np.ndarray
            Array read from file.
        """

        if self._map is None:
            base_map = enmap.read_map(str(self.filename))

            if len(base_map.shape) == 2:
                self._map = base_map
            else:
                if isinstance(self.identifier, int):
                    self._map = base_map[self.identifier]
                elif isinstance(self.identifier, str):
                    index = StokesParameters[self.identifier].value
                    self._map = base_map[index]
                elif self.identifier is None:
                    raise ValueError("You must provide an identifier for a 3D array.")

        return self._map

    def world_width(self) -> tuple[int]:
        return (
            self.read_data()
            .submap([[-math.pi / 2, -math.pi], [math.pi / 2, math.pi]])
            .shape
        )

    def world_full_array_size(self) -> tuple[int]:
        return list(
            reversed(
                [
                    self.header.get(f"NAXIS{x}")
                    for x in range(1, self.header.get("NAXIS", 0) + 1)
                ]
            )
        )

    def histogram_raw_data(
        self, n_bins: int, min: float, max: float
    ) -> tuple[np.array]:
        """
        Generate a histogram of the raw data, with a given range and number of bins.
        """

        bins = np.linspace(min, max, n_bins + 1)

        if self.log_scale_data:
            not_zeros = self.read_data() != 0.0
            data = np.log10(np.abs(self.read_data()[not_zeros]))
        else:
            data = self.read_data()

        H, edges = np.histogram(data, bins=bins)

        return H, edges

    def world_size_degrees(self) -> tuple[tuple[units.Quantity]]:
        """
        Returns the top right and bottom left tuple for ra and dec, supprts
        ra, dec as properties.
        """
        ra_world_width, dec_world_width = self.world_width()

        top_right = self.wcs.array_index_to_world(*[0] * self.header.get("NAXIS", 2))
        bottom_left = self.wcs.array_index_to_world(
            *[x - 1 for x in self.world_full_array_size()]
        )

        sanitize = lambda x: (
            x[0].ra if x[0].ra < 180.0 * units.deg else x[0].ra - 360.0 * units.deg,
            x[0].dec if x[0].dec < 90.0 * units.deg else x[0].dec - 180.0 * units.deg,
        )

        sanitize_nonscalar = lambda x: (
            x.ra if x.ra < 180.0 * units.deg else x.ra - 360.0 * units.deg,
            x.dec if x.dec < 90.0 * units.deg else x.dec - 180.0 * units.deg,
        )

        try:
            return sanitize(top_right), sanitize(bottom_left)
        except TypeError:
            return sanitize_nonscalar(top_right), sanitize_nonscalar(bottom_left)

    @property
    def tile_size(self) -> int:
        if self._tile_size is not None:
            return self._tile_size

        # Need to figure out how big the whole 'map' is, i.e. moving it up
        # so that it fills the whole space.

        map_size_x, map_size_y = self.world_width()
        max_size = max(map_size_x, map_size_y)

        # See if 256 fits.
        if (map_size_x % 256 == 0) and (map_size_y % 256 == 0):
            self._tile_size = 256
            self._number_of_levels = int(math.log2(max_size // 256))
            return self.tile_size

        # Oh no, remove all the powers of two until
        # we get an odd number.
        this_tile_size = map_size_y

        # Also don't make it too small.
        while this_tile_size % 2 == 0 and this_tile_size > 512:
            this_tile_size = this_tile_size // 2

        self._number_of_levels = int(math.log2(max_size // this_tile_size))
        self._tile_size = this_tile_size

        return self.tile_size

    @property
    def number_of_levels(self) -> int:
        if self._number_of_levels is None:
            # Side effect sets _number_of_levels.
            _ = self.tile_size

        return self._number_of_levels

    def get_tile(self, zoom: int, x: int, y: int):
        # RA is covered by -180 to 180 degrees, and 2 tiles at zoom 0
        # Dec is covered by -90 to 90 degrees, and 1 tile at zoom 0.

        RA_OFFSET = -np.pi
        RA_RANGE = 2.0 * np.pi
        DEC_OFFSET = -0.5 * np.pi
        DEC_RANGE = np.pi

        ra_per_tile = RA_RANGE / 2 ** (zoom + 1)
        dec_per_tile = DEC_RANGE / 2 ** (zoom)

        ra = lambda v: (ra_per_tile * v + RA_OFFSET)
        dec = lambda v: (dec_per_tile * v + DEC_OFFSET)

        def pix(v, w):
            return (ra(v), dec(w))

        bottom_left = pix(x, y)
        top_right = pix(x + 1, y + 1)

        return bottom_left, top_right

    def read_tile(self, zoom: int, x: int, y: int) -> np.ndarray:
        bottom_left, top_right = self.get_tile(zoom=zoom, x=x, y=y)

        enmap_slice = np.array(
            [[bottom_left[1], bottom_left[0]], [top_right[1], top_right[0]]]
        )

        assert np.isclose(
            abs(bottom_left[0] - top_right[0]), abs(bottom_left[1] - top_right[1]), 1e-5
        )

        submap = self.read_data().submap(enmap_slice)

        if self.log_scale_data:
            not_zeros = submap != 0.0
            submap[not_zeros] = np.log10(np.abs(submap[not_zeros]))
            submap[np.logical_not(not_zeros)] = np.nan

        return submap


class FITSTile:
    """
    Tile in the QuadTree
    """

    x: int
    y: int
    zoom: int
    data: Optional[np.ndarray] = None
    children: Optional[list["FITSTile"]] = None

    def __init__(self, x: int, y: int, zoom: int):
        self.x = x
        self.y = y
        self.zoom = zoom

        return

    def create_children(self):
        new_zoom_level = self.zoom + 1
        starting_x = self.x * 2
        starting_y = self.y * 2

        self.children = [
            [FITSTile(starting_x + x, starting_y + y, new_zoom_level)]
            for x in range(2)
            for y in range(2)
        ]

        return

    def create_data_from_children(self):
        if self.children is None:
            raise ValueError(
                "Cannot create data from children if children are not present."
            )

        valid_child = None

        for child_row in self.children:
            for child in child_row:
                if child.data is not None:
                    valid_child = child
                    break

        if valid_child is None:
            self.data = None

            return

        data_shape = valid_child.data.shape
        buffer_shape = [d * 2 for d in data_shape]
        data_type = valid_child.data.dtype

        # Buffer shape should be square.
        assert buffer_shape[0] == buffer_shape[1]

        data_buffer = np.zeros(buffer_shape, dtype=data_type)
        mask_buffer = np.zeros(buffer_shape, dtype=bool)

        # (1, 0) (1, 1)
        # (0, 0) (0, 1)

        for y in range(2):
            for x in range(2):
                child_data = self.children[y][x].data

                covered_region = np.s_[
                    y * data_shape[0] : (y + 1) * data_shape[0],
                    x * data_shape[1] : (x + 1) * data_shape[1],
                ]

                if child_data is None:
                    # Empty region. Mask it out!
                    mask_buffer[covered_region] = True
                    continue

                data_buffer[covered_region] = 0.25 * child_data

                if isinstance(child_data, np.ma.MaskedArray):
                    mask_buffer[covered_region] = child_data.mask
                else:
                    pass

        data = (
            data_buffer[::2, ::2]
            + data_buffer[1::2, ::2]
            + data_buffer[::2, 1::2]
            + data_buffer[1::2, 1::2]
        )

        if mask_buffer.any():
            mask = np.logical_and.reduce(
                [
                    mask_buffer[::2, ::2],
                    mask_buffer[1::2, ::2],
                    mask_buffer[::2, 1::2],
                    mask_buffer[1::2, 1::2],
                ]
            )

            self.data = np.ma.MaskedArray(data, mask=mask)
        else:
            self.data = data

        return


class Layer:
    zoom: int
    nx: int
    ny: int
    nodes: list[list[FITSTile]]
    upper: Optional["Layer"] = None
    lower: Optional["Layer"] = None

    def __init__(self, zoom: int):
        self.zoom = zoom
        self.nx = 2 ** (zoom + 1)
        self.ny = 2**zoom

        self.create_empty_nodes()

    def create_empty_nodes(self):
        self.nodes = [
            [FITSTile(x, y, self.zoom) for x in range(self.nx)] for y in range(self.ny)
        ]

    def link_to_lower_layer(self, lower_layer: "Layer"):
        for y, node_row in enumerate(self.nodes):
            for x, node in enumerate(node_row):
                node.children = [
                    [lower_layer[y * 2, x * 2], lower_layer[y * 2, x * 2 + 1]],
                    [lower_layer[y * 2 + 1, x * 2], lower_layer[y * 2 + 1, x * 2 + 1]],
                ]

    def create_lower_layer(self) -> "Layer":
        new_layer = Layer(self.zoom + 1)
        new_layer.upper = self
        self.lower = new_layer

        self.link_to_lower_layer(new_layer)

        return new_layer

    def create_data_from_children(self):
        for node_row in self.nodes:
            for node in node_row:
                if node.data is None:
                    node.create_data_from_children()

    def extract_data_from_image(self, image: FITSSimpleLoader, image_pixel_size: int):
        for node_row in self.nodes:
            for node in node_row:
                potential_tile = image.read_tile(node.zoom, node.x, node.y)

                if (potential_tile == 0.0).all():
                    potential_tile = None

                node.data = potential_tile

    def __getitem__(self, key: tuple[int]):
        y, x = key
        return self.nodes[y][x]


class LayerTree:
    initialized: bool = False

    def __init__(
        self, number_of_layers: int, image_pixel_size: int, image: FITSSimpleLoader
    ):
        self.number_of_layers = number_of_layers
        self.image_pixel_size = image_pixel_size
        self.image = image

        self.top_layer = Layer(0)

        self.layers = [self.top_layer]

        current_layer = self.top_layer

        for _ in range(1, number_of_layers):
            current_layer = current_layer.create_lower_layer()

            self.layers.append(current_layer)

        current_layer.extract_data_from_image(image, image_pixel_size)

        for layer in reversed(self.layers[:-1]):
            layer.create_data_from_children()

        self.initialized = True

        return

    def get_tile(self, zoom: int, x: int, y: int) -> FITSTile:
        return self.layers[zoom].nodes[y][x]
