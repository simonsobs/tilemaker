"""
A simple map example. Given an array with dimensions 2:1, we assume
that the array covers the entire world. Then making the tiles is
a simple operation of splitting the array into smaller and smaller
chunks.
"""

import numpy as np
from pydantic import BaseModel, validator
from pydantic_numpy.typing import NpNDArray


class SimpleMapMaker(BaseModel):
    raw_array: NpNDArray

    _tile_size: int | None = None
    _tiles: dict[int, dict[str, NpNDArray]] | None = None

    @validator("raw_array")
    def check_dimensions(cls, v):
        if len(v.shape) != 2:
            raise ValueError("Array must be 2D.")
        if v.shape[0] // v.shape[1] != 2:
            raise ValueError("Array must have dimensions 2:1.")
        return v

    @property
    def tile_size(self):
        # Find a reasonable tile size for the array. This will
        # be the smallest power of two that divides the array.
        # Though if we can get away with 256, let's just use
        # that.
        if self._tile_size is not None:
            return self._tile_size

        if self.raw_array.shape[0] % 256 == 0:
            self._tile_size = 256
            return self.tile_size
        else:
            # Deal with this later
            raise NotImplementedError

    def make_tiles(self):
        if self._tiles is not None:
            return self._tiles

        number_of_levels = int(np.log2(self.raw_array.shape[0] // self.tile_size)) - 1

        tile_size = self.tile_size
        levels = {}
        copy_array = self.raw_array.copy()

        for level in reversed(range(number_of_levels + 1)):
            tiles = {}

            if copy_array.shape[1] < tile_size:
                raise ValueError("Array is too small for tile size.")

            for x in range(0, copy_array.shape[0] // tile_size):
                for y in range(0, copy_array.shape[1] // tile_size):
                    x_range = np.s_[x * tile_size : (x + 1) * tile_size]
                    y_range = np.s_[y * tile_size : (y + 1) * tile_size]
                    tile = copy_array[x_range, y_range]

                    tiles[f"{x}_{y}"] = tile

            levels[level] = tiles

            if level != 0:
                # Reduce the array size for the next level.
                tl = copy_array[::2, ::2]
                tr = copy_array[1::2, ::2]
                bl = copy_array[::2, 1::2]
                br = copy_array[1::2, 1::2]

                copy_array = 0.25 * (tl + tr + bl + br)

        return levels

    def get_tile(self, x: int, y: int, level: int):
        return self.make_tiles()[level][f"{x}_{y}"]
