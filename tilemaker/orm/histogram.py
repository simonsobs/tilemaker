"""
ORM object for the histogramming function. We pre-generate
histograms for all the entered Band(s) such that we can use this
to set colour maps.
"""

from sqlmodel import Field, Relationship, SQLModel

from .map import Band


class Histogram(SQLModel, table=True):
    id: int = Field(primary_key=True, description="The id of the histogram.")
    band_id: int = Field(
        foreign_key="band.id",
        description="The band that this histogram is associated with.",
    )
    band: Band = Relationship(back_populates="histogram")

    start: float = Field(description="The left edge of the bins.")
    end: float = Field(description="The right edge of the bins.")
    bins: int = Field(description="The number of bins.")

    edges_data_type: str = Field(description="The data type of the underlying data.")
    edges: bytes = Field(
        description="The bin edges, stored as the associated data type."
    )

    histogram_data_type: str = Field(description="The data type of the histogram data.")
    histogram: bytes = Field(
        description="The histogram data, stored as the associated data type."
    )
