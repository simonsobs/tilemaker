"""
Metadata about a map.

Links out to the table that contain the actual map (tile) data. Each
map correpsonds to a single frequency band.
"""

from typing import TYPE_CHECKING

import astropy.wcs
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .histogram import Histogram
    from .tiles import Tile


class MapBase(SQLModel):
    id: int = Field(primary_key=True)
    name: str = Field(max_length=255, description="The name of the map.")
    description: str | None = Field(
        default=None, max_length=255, description="A description of the map."
    )


class Map(MapBase, table=True):
    __tablename__ = "map"

    bands: list["Band"] = Relationship(
        back_populates="map", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    def __str__(self):
        return f"Map {self.id} with name {self.name} and description {self.description}"


class MapResponse(MapBase):
    bands: list["Band"]


class Band(SQLModel, table=True):
    id: int = Field(primary_key=True, description="The id of this band information.")

    map_id: int = Field(
        foreign_key="map.id", description="The name of the map that this links to."
    )
    map_name: str = Field(description="The name of the map that this band is from.")
    map: Map = Relationship(
        back_populates="bands",
    )

    bounding_left: float | None
    bounding_right: float | None
    bounding_top: float | None
    bounding_bottom: float | None

    quantity: str | None = Field(
        default=None, description="The quantity that the map is of."
    )
    units: str | None = Field(default=None, description="The units that the map is in.")

    recommended_cmap_min: float | None = Field(
        default=None,
        description="The recommended minimum value for the colour map. Should be the starting value.",
    )
    recommended_cmap_max: float | None = Field(
        default=None,
        description="The recommended maximum value for the colour map. Should be the starting value.",
    )
    recommended_cmap: str | None = Field(
        default=None, description="The default colour map for this band."
    )

    tiles_available: bool = Field(
        default=False, description="Whether or not tiles are available for this band."
    )
    levels: int = Field(
        description="The number of levels of tiles available for this band."
    )
    tile_size: int = Field(description="The size of the tiles in pixels.")
    tiles: list["Tile"] = Relationship(
        back_populates="band", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    histogram: "Histogram" = Relationship(
        back_populates="band", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    def __str__(self):
        return (
            f"Band {self.id} with quantity {self.quantity} and units {self.units} from map {self.map_name} "
            f"with {self.levels} levels of tiles available at size {self.tile_size} pixels."
        )

    @property
    def wcs(self, level: int | None = None) -> astropy.wcs.WCS:
        """
        Get the WCS solution for this band.  Note that we don't expect this to be the same
        layout as the original map file; we have effecftively re-projected the map into a whole

        """

        if level is None:
            level = self.levels

        pix_x = 2**level * self.tile_size
        pix_y = 2 ** (level - 1) * self.tile_size

        crpix = [pix_x / 2, pix_y / 2]
        crdelt = [-(360) / pix_x, (180) / pix_y]
        crval = [0.0, 0.0]

        wcs = astropy.wcs.WCS(
            naxis=2,
        )

        wcs.wcs.crpix = crpix
        wcs.wcs.cdelt = crdelt
        wcs.wcs.crval = crval
        wcs.wcs.ctype = ["RA---CAR", "DEC--CAR"]
        wcs.wcs.cunit = ["deg", "deg"]

        return wcs
