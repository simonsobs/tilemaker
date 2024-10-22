"""
Spec for the tiles themselves.

They are indexed in FOUR ways:
    - Level
    - x, y
    - band_id
"""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .map import Band


class Tile(SQLModel, table=True):
    # All of these (level, x, y, band_id) could potentially
    # be a composite primary key, but we're going to use a
    # single primary key for simplicity.
    level: int = Field(primary_key=True, description="The level of this tile.")
    x: int = Field(primary_key=True, description="The x coordinate of this tile.")
    y: int = Field(primary_key=True, description="The y coordinate of this tile.")
    band_id: int = Field(
        primary_key=True,
        foreign_key="band.id",
        description="The id of the band this tile belongs to.",
    )
    band: "Band" = Relationship(back_populates="tiles")

    data_type: str | None = Field(
        description="The data type of the underlying tile data."
    )
    data: bytes | None = Field(description="The actual tile data.")
