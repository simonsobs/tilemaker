"""
A source table that can be displayed on top of the map.
"""

from sqlmodel import Field, Relationship, SQLModel


class SourceListBase(SQLModel):
    id: int = Field(primary_key=True)
    name: str
    description: str | None = Field(default=None)


class SourceList(SourceListBase, table=True):
    __tablename__ = "source_list"

    sources: list["SourceItem"] = Relationship(
        back_populates="source_list",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    def __str__(self):
        return f"Source list {self.id} with name {self.name} and description {self.description}"


class SourceItemBase(SQLModel):
    id: int = Field(primary_key=True)
    flux: float = Field(description="The flux of the source.")
    ra: float = Field(description="The right ascension of the source.")
    dec: float = Field(description="The declination of the source.")
    name: str | None = Field(default=None, description="The name of the source.")


class SourceItem(SourceItemBase, table=True):
    __tablename__ = "source_item"

    source_list_id: int = Field(
        foreign_key="source_list.id",
        description="The ID of the source list that this links to.",
    )
    source_list: SourceList = Relationship(
        back_populates="sources",
    )
