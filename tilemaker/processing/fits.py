"""
FITS file handling using the WCS utilities.
"""

import math
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import numpy as np
from astropy import units
from astropy.coordinates import SkyCoord, StokesCoord
from astropy.io import fits
from astropy.wcs import WCS
from pydantic import BaseModel

COORD_TOL = 1e-3


class MapProjectionEnum(Enum):
    EQUIRECTANGULAR = "EQUIRECTANGULAR"


class StokesParameters(Enum):
    I = 0
    Q = 1
    U = 2


class Map(BaseModel):
    identifier: Optional[Union[str, int]]


class FITSFile(BaseModel):
    """
    A FITS file that can link out to multiple underlying
    'bands', notably different Stokes parameters.
    """

    filename: Path
    "The filename of the FITS file."

    @property
    def individual_trees(self) -> list["FITSImage"]:
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
                else:
                    if "NAXIS3" in hdu.header:
                        # Hmm, this is a bit of a problem. Just assume it's stokes?
                        hdu.header["CTYPE3"] = "STOKES"
                        hdu.header["CDELT3"] = 1.0
                        for stokes in StokesParameters:
                            hdus.append((i, stokes.name))

                    hdus.append((i, None))

        return [
            FITSImage(self.filename, hdu=i, identifier=stokes) for i, stokes in hdus
        ]


class FITSImage:
    filename: Path
    "Filename to read from. Will be converted to a Path if required."
    hdu: int
    "Header data unit to use. One per object."
    identifier: Optional[Union[str, int]] = None
    "Identifier for the data array to read. One per object."

    header: Optional[fits.header.Header] = None
    "Header object from astropy"
    wcs: Optional[WCS] = None
    "World co-ordinate system for this file"

    _tile_size: Optional[int] = None
    "Size of the tiles to read from the file."
    _number_of_levels: Optional[int] = None

    def __init__(
        self, filename: Path, hdu: int = 0, identifier: Optional[Union[str, int]] = None
    ):
        """
        Parameters
        ----------
        identifier : Union[str, int], optional
            Identifier of the index to read. If your array has three dimensions,
            you must provide this. It can be an integer, or a string in the case
            where you have a well defiend `CTYPE3` in your header. Accepted values
            `CTYPE3`:

            * `STOKES`, which implies three arrays in order of IQU
        """
        self.filename = Path(filename)
        self.hdu = hdu
        self.identifier = identifier

        self.read_metadata()

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
            tile_size = self.tile_size

        return self._number_of_levels

    def read_metadata(self):
        with fits.open(self.filename) as handle:
            self.header = handle[self.hdu].header
            self.wcs = WCS(self.header)

    def read_data(self) -> np.ndarray:
        """
        Read the data array for the file given the identifier.

        Returns
        -------
        np.ndarray
            Array read from file.
        """

        if self.wcs is None:
            self.read_metadata()

        if self.header["NAXIS"] == 2:
            with fits.open(self.filename) as handle:
                return handle[self.hdu].data

        index = None
        identifier = self.identifier

        if isinstance(identifier, int):
            index = identifier
        elif isinstance(identifier, str):
            if self.header["CTYPE3"] == "STOKES":
                index = StokesParameters[identifier].value
            else:
                raise ValueError(
                    f"Unknown identifier {identifier} for CTYPE3 {self.header['CTYPE3']}."
                )
        elif identifier is None:
            raise ValueError("You must provide an identifier for a 3D array.")

        with fits.open(self.filename) as handle:
            return handle[self.hdu].data[index]

    @property
    def projection(self) -> MapProjectionEnum:
        """
        The projection that this image is in.
        """

        if self.header is None:
            self.read_metadata()

        if "CAR" in self.header["CTYPE1"]:
            return MapProjectionEnum.EQUIRECTANGULAR

        raise ValueError(f"Unknown projection {self.header['CTYPE1']}.")

    def available_maps(self) -> list[Map]:
        if self.header["NAXIS"] == 2:
            return [Map(identifier=None)]
        elif self.header["CTYPE3"] == "STOKES":
            return [Map(identifier=e.name) for e in StokesParameters]
        else:
            return [Map(identifier=i) for i in range(int(self.header["NAXIS3"]))]

    def axes(self) -> tuple[int, int]:
        """
        Gets the RA, and Dec axes.
        """

        # Identify which axis in the map corresponds to RA and DEC

        ra_axis = None
        dec_axis = None

        # Axis selection is inverted in FITS, so we have to index the other way around (i.e. use -ra_axis)

        if "RA" in self.header["CTYPE1"]:
            ra_axis = 1
        elif "DEC" in self.header["CTYPE1"]:
            dec_axis = 1
        else:
            raise ValueError(
                f"Unable to interpret value of CTYPE1={self.header['CTYPE1']}."
            )

        if "RA" in self.header["CTYPE2"]:
            ra_axis = 2
        elif "DEC" in self.header["CTYPE2"]:
            dec_axis = 2
        else:
            raise ValueError(
                f"Unable to interpret value of CTYPE2={self.header['CTYPE2']}."
            )

        if ra_axis is None:
            raise ValueError(
                "Unable to find which axis represents RA in the map. Set CTYPE1 or CTYPE2 to contain RA"
            )

        if dec_axis is None:
            raise ValueError(
                "Unable to find which axis represents DEC in the map. Set CTYPE1 or CTYPE2 to contain DEC"
            )

        return ra_axis, dec_axis

    def world_full_array_size(self) -> tuple[int]:
        return list(
            reversed(
                [
                    self.header.get(f"NAXIS{x}")
                    for x in range(1, self.header.get("NAXIS", 0) + 1)
                ]
            )
        )

    def world_width(self) -> tuple[int, int]:
        """
        Get the ra and dec world width.
        """

        ra_axis, dec_axis = self.axes()

        # Identify the pixel scale in RA and DEC
        deg_per_pix_ra = self.header[f"CDELT{ra_axis}"]
        deg_per_pix_dec = self.header[f"CDELT{dec_axis}"]

        if abs(deg_per_pix_ra) != abs(deg_per_pix_dec):
            raise ValueError(
                "Pixel scale in RA and DEC are not equal. Map is not in equi-rectangular projection."
            )

        COORD_TOL = 1e-6 * abs(deg_per_pix_dec)
        # Identify the bottom left pixel. Don't forget RA goes right to left.
        # TODO: Be careful about stokes!
        bottom_left = self.wcs.world_to_array_index(
            SkyCoord((180 - COORD_TOL) * units.deg, (-90 + COORD_TOL) * units.deg),
            StokesCoord("I"),
        )

        # Identify the top right pixel
        top_right = self.wcs.world_to_array_index(
            SkyCoord((-180 + COORD_TOL) * units.deg, (90 - COORD_TOL) * units.deg),
            StokesCoord("I"),
        )

        # Those pixels are now re-mapped to (0, 0), (N, M) in our new space that covers the whole map.
        # We can easily calculate offsets.

        ra_world_width = top_right[-ra_axis] - bottom_left[-ra_axis]
        dec_world_width = top_right[-dec_axis] - bottom_left[-dec_axis]

        n_pix_ra = self.header[f"NAXIS{ra_axis}"]
        n_pix_dec = self.header[f"NAXIS{dec_axis}"]

        if ra_world_width < n_pix_ra:
            ra_world_width = n_pix_ra

        if dec_world_width < n_pix_dec:
            dec_world_width = n_pix_dec

        print(bottom_left, top_right)
        print(ra_world_width, dec_world_width)

        return ra_world_width, dec_world_width

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

        print("World size:", sanitize(top_right), sanitize(bottom_left))

        return sanitize(top_right), sanitize(bottom_left)

    def slice_raw_data(
        self, slice: np.s_
    ) -> Optional[Union[np.ma.MaskedArray, np.ndarray]]:
        """
        Slices the raw data with provided slice. Returns data assuming that the
        map spans the range (-180, 180) in RA, and (-90, 90) in declination in a
        pixel grid defined by the largest of the two axes.

        If the grid contains no valid data from the original map, returns None.

        If the requested slice overlaps perfectly with the map, a view of the
        original map in memory is returned.

        If the slice partially overlaps with the map, a masked array is returned.

        TODO: Need to push map data down into Map so we can use different maps from
              same file.

        Parameters
        ----------
        slice : np.s_
            Slice into map space. Pixels are indexed in order (ra, dec)

        Returns
        -------
        Optional[np.ndarray]
            Array containing the sliced data. Returns None if there is no viable overlap
            with the map and the requested slice.
        """

        # TODO: See above. This is obviously super slow.
        if not hasattr(self, "data"):
            self.data = self.read_data()

        ra_axis, dec_axis = self.axes()

        n_pix_ra = self.header[f"NAXIS{ra_axis}"]
        n_pix_dec = self.header[f"NAXIS{dec_axis}"]

        # Identify the pixel scale in RA and DEC
        deg_per_pix_ra = self.header[f"CDELT{ra_axis}"]
        deg_per_pix_dec = self.header[f"CDELT{dec_axis}"]

        if abs(deg_per_pix_ra) != abs(deg_per_pix_dec):
            raise ValueError(
                "Pixel scale in RA and DEC are not equal. Map is not in equi-rectangular projection."
            )

        COORD_TOL = 1e-3 * abs(deg_per_pix_dec)
        # Identify the bottom left pixel. Don't forget RA goes right to left.
        # TODO: Be careful about stokes!
        bottom_left = self.wcs.world_to_array_index(
            SkyCoord((180 - COORD_TOL) * units.deg, (-90 + COORD_TOL) * units.deg),
            StokesCoord("I"),
        )

        # Identify the top right pixel
        top_right = self.wcs.world_to_array_index(
            SkyCoord((-180 + COORD_TOL) * units.deg, (90 - COORD_TOL) * units.deg),
            StokesCoord("I"),
        )

        start_ra = bottom_left[-ra_axis]
        start_dec = bottom_left[-dec_axis]

        # Now we just have a linear offset. Our world is (0, 0) to (ra_world_width, dec_world_width).
        # Our image goes from (-start_ra, -start_dec) to (n_pix_ra - start_ra, n_pix_dec - start_dec).

        ra_range_world = (slice[0].start, slice[0].stop)
        dec_range_world = (slice[1].start, slice[1].stop)

        ra_range_array = [i + start_ra for i in ra_range_world]
        dec_range_array = [i + start_dec for i in dec_range_world]

        # Now we have the range in array space. We can use this to slice the array.

        ra_range_entirely_within_map = (
            ra_range_array[0] >= 0 and ra_range_array[1] <= n_pix_ra
        )

        dec_range_entirely_within_map = (
            dec_range_array[0] >= 0 and dec_range_array[1] <= n_pix_dec
        )

        if ra_range_entirely_within_map and dec_range_entirely_within_map:
            if ra_axis > dec_axis:
                return self.data[
                    ra_range_array[0] : ra_range_array[1],
                    dec_range_array[0] : dec_range_array[1],
                ]
            else:
                return self.data[
                    dec_range_array[0] : dec_range_array[1],
                    ra_range_array[0] : ra_range_array[1],
                ]

        ra_range_outside_of_map = (ra_range_array[0] < 0 and ra_range_array[1] < 0) or (
            ra_range_array[0] > n_pix_ra and ra_range_array[1] > n_pix_ra
        )

        dec_range_outside_of_map = (
            dec_range_array[0] < 0 and dec_range_array[1] < 0
        ) or (dec_range_array[0] > n_pix_dec and dec_range_array[1] > n_pix_dec)

        if ra_range_outside_of_map or dec_range_outside_of_map:
            return None

        # Most complex: we have a partial overlap. We need to mask the array.

        d_ra = ra_range_array[1] - ra_range_array[0]
        d_dec = dec_range_array[1] - dec_range_array[0]

        if ra_axis > dec_axis:
            buffer_shape = (d_ra, d_dec)
        else:
            buffer_shape = (d_dec, d_ra)

        data_buffer = np.zeros(buffer_shape, dtype=self.data.dtype, order="C")

        mask_buffer = np.ones(buffer_shape, dtype=bool)

        input_start_ra = max(0, ra_range_array[0])
        input_end_ra = min(n_pix_ra, ra_range_array[1])

        input_start_dec = max(0, dec_range_array[0])
        input_end_dec = min(n_pix_dec, dec_range_array[1])

        if ra_axis > dec_axis:
            input_selector = np.s_[
                input_start_ra:input_end_ra, input_start_dec:input_end_dec
            ]
        else:
            input_selector = np.s_[
                input_start_dec:input_end_dec, input_start_ra:input_end_ra
            ]

        # Transform back to world co-ordinates, then remove bottom left of buffer.
        output_start_ra = input_start_ra - start_ra - slice[0].start
        output_end_ra = input_end_ra - start_ra - slice[0].start

        output_start_dec = input_start_dec - start_dec - slice[1].start
        output_end_dec = input_end_dec - start_dec - slice[1].start

        if ra_axis > dec_axis:
            output_selector = np.s_[
                output_start_ra:output_end_ra, output_start_dec:output_end_dec
            ]
        else:
            output_selector = np.s_[
                output_start_dec:output_end_dec, output_start_ra:output_end_ra
            ]

        try:
            data_buffer[output_selector] = self.data[input_selector]
            mask_buffer[output_selector] = False
        except ValueError:
            import pdb

            pdb.set_trace()

        return np.ma.MaskedArray(data_buffer, mask=mask_buffer)

    def histogram_raw_data(
        self, n_bins: int, min: float, max: float
    ) -> tuple[np.array]:
        """
        Generate a histogram of the raw data, with a given range and number of bins.
        """

        bins = np.linspace(min, max, n_bins + 1)

        H, edges = np.histogram(self.read_data(), bins=bins)

        return H, edges


class FITSTile:
    """
    Tile in the QuadTree
    """

    x: int
    y: int
    zoom: int
    data: Optional[np.ndarray] = None
    children: Optional[list["Tile"]] = None

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

    def extract_data_from_image(self, image: FITSImage, image_pixel_size: int):
        for node_row in self.nodes:
            for node in node_row:
                selector = np.s_[
                    node.x * image_pixel_size : (node.x + 1) * image_pixel_size,
                    node.y * image_pixel_size : (node.y + 1) * image_pixel_size,
                ]

                raw_data = image.slice_raw_data(selector)

                if raw_data is not None:
                    if raw_data.dtype.byteorder != "=":
                        raw_data = raw_data.byteswap().newbyteorder("=")

                node.data = raw_data

    def __getitem__(self, key: tuple[int]):
        y, x = key
        return self.nodes[y][x]


class LayerTree:
    initialized: bool = False

    def __init__(self, number_of_layers: int, image_pixel_size: int, image: FITSImage):
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
