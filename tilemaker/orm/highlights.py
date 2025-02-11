"""
ORM for highlight areas. Highlight areas are parts of the map that
are drawn as (optional) boxes in the UI that persist between pages.
"""

from sqlmodel import Field, SQLModel


class HighlightBoxBase(SQLModel):
    id: int = Field(primary_key=True)
    name: str
    description: str | None = Field(default=None)
    top_left_ra: float
    top_left_dec: float
    bottom_right_ra: float
    bottom_right_dec: float


class HighlightBox(HighlightBoxBase, table=True):
    __tablename__ = "highlight_box"
