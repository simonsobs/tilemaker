"""
Metadata about a map.

Links out to the table that contain the actual map (tile) data. Each
map correpsonds to a single frequency band.
"""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .histogram import Histogram
    from .tiles import Tile


class MapBase(SQLModel):
    id: int = Field(primary_key=True)
    name: str = Field(
        max_length=255, description="The name of the map."
    )
    description: str | None = Field(
        default=None, max_length=255, description="A description of the map."
    )
    telescope: str | None = Field(
        default=None,
        max_length=255,
        description="The telescope that was used to create this map.",
    )
    data_release: str | None = Field(
        default=None,
        max_length=255,
        description="The data release that this map is part of.",
    )
    season: str | None = Field(
        default=None,
        max_length=255,
        description="The season that this map was taken in.",
    )
    tags: str | None = Field(
        default=None,
        max_length=255,
        description="Any tags that are associated with this map.",
    )
    patch: str | None = Field(
        default=None,
        max_length=255,
        description="The patch of the sky that this map covers.",
    )


class Map(MapBase, table=True):
    __tablename__ = "map"

    bands: list["Band"] = Relationship(
        back_populates="map", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    def __str__(self):
        return (
            f"Map {self.id} with name {self.name} and description {self.description} from telescope {self.telescope} "
            f"with data release {self.data_release} and season {self.season}; tags: {self.tags}; patch: {self.patch}"
        )


class MapResponse(MapBase):
    bands: list["Band"]


class Band(SQLModel, table=True):
    id: int = Field(primary_key=True, description="The id of this band information.")

    map_name: str = Field(
        foreign_key="map.name", description="The name of the map that this links to."
    )
    map: Map = Relationship(
        back_populates="bands",
    )

    bounding_left: float | None
    bounding_right: float | None
    bounding_top: float | None
    bounding_bottom: float | None

    frequency: float | None = Field(
        default=None, description="The frequency of this band in GHz"
    )
    stokes_parameter: str | None = Field(
        default=None, max_length=255, description="The Stokes parameter of this band."
    )

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
            f"Band {self.id} with frequency {self.frequency} GHz and Stokes parameter {self.stokes_parameter} "
            f"with {self.levels} levels of tiles available at size {self.tile_size} pixels."
        )
