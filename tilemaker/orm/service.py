"""
Service description in the database. A simple
single row table.
"""

from sqlmodel import Field, SQLModel


class Service(SQLModel, table=True):
    name: str = Field(
        default="Untitled",
        primary_key=True,
        max_length=255,
        description="The name of the service.",
    )
    description: str = Field(
        default="A tilemaker service.",
        max_length=255,
        description="A description of the service.",
    )
    max_cache_size: int = Field(
        default=16, description="The maximum number of fits files to cache."
    )
