"""
Metadata about a map.

Links out to the table that contain the actual map (tile) data. Each
map correpsonds to a single frequency band.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .tiles import Tile


class MapBase(SQLModel):
    name: str = Field(
        primary_key=True,
        max_length=255,
        description="The name of the map."
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        description="A description of the map."
    )

class Map(MapBase, table=True):
    __tablename__ = "map"

    bands: list["Band"] = Relationship(back_populates="map", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class MapResponse(MapBase):
    bands: list["Band"]

class Band(SQLModel, table=True):
    id: int = Field(
        primary_key=True,
        description="The id of this band information."
    )

    map_name: str = Field(
        foreign_key="map.name",
        description="The name of the map that this links to."
    )
    map: Map = Relationship(
        back_populates="bands",
    )

    bounding_left: float | None
    bounding_right: float | None
    bounding_top: float | None
    bounding_bottom: float | None

    frequency: float | None = Field(
        default=None,
        description="The frequency of this band in GHz"
    )
    stokes_parameter: str | None = Field(
        default=None,
        max_length=255,
        description="The Stokes parameter of this band."
    )

    units: str | None = Field(
        default=None,
        description="The units that the map is in."
    )
    recommended_cmap_min: float | None = Field(
        default=None,
        description="The recommended minimum value for the colour map. Should be the starting value."
    )
    recommended_cmap_max: float | None = Field(
        default=None,
        description="The recommended maximum value for the colour map. Should be the starting value."
    )
    recommended_cmap: str | None = Field(
        default=None,
        description="The default colour map for this band."
    )

    tiles_available: bool = Field(
        default=False,
        description="Whether or not tiles are available for this band."
    )
    levels: int = Field(
        description="The number of levels of tiles available for this band."
    )
    tile_size: int = Field(
        description="The size of the tiles in pixels."
    )
    tiles: list["Tile"] = Relationship(back_populates="band", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
