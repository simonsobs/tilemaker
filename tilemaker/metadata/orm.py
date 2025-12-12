"""
SQLAlchemy ORM models for the metadata database.
"""

from sqlalchemy import (
    JSON,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class MapGroupORM(Base):
    __tablename__ = "map_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    grant = Column(String)

    maps = relationship(
        "MapORM",
        back_populates="map_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MapORM(Base):
    __tablename__ = "maps"

    id = Column(Integer, primary_key=True)
    map_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    grant = Column(String)
    map_group_id = Column(
        Integer, ForeignKey("map_groups.id", ondelete="CASCADE"), nullable=False
    )

    map_group = relationship("MapGroupORM", back_populates="maps")
    bands = relationship(
        "BandORM",
        back_populates="map",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class BandORM(Base):
    __tablename__ = "bands"

    id = Column(Integer, primary_key=True)
    band_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    grant = Column(String)
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)

    map = relationship("MapORM", back_populates="bands")
    layers = relationship(
        "LayerORM",
        back_populates="band",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LayerORM(Base):
    __tablename__ = "layers"

    id = Column(Integer, primary_key=True)
    layer_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    grant = Column(String)
    band_id = Column(
        Integer, ForeignKey("bands.id", ondelete="CASCADE"), nullable=False
    )

    quantity = Column(String)
    units = Column(String)

    number_of_levels = Column(Integer)
    tile_size = Column(Integer)

    vmin = Column(String)  # Can be float or 'auto'
    vmax = Column(String)  # Can be float or 'auto'
    cmap = Column(String)

    # Provider information stored as JSON
    provider = Column(JSON, nullable=False)

    # Bounding box
    bounding_left = Column(Float)
    bounding_right = Column(Float)
    bounding_top = Column(Float)
    bounding_bottom = Column(Float)

    band = relationship("BandORM", back_populates="layers")


class BoxORM(Base):
    __tablename__ = "boxes"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    top_left_ra = Column(Float, nullable=False)
    top_left_dec = Column(Float, nullable=False)
    bottom_right_ra = Column(Float, nullable=False)
    bottom_right_dec = Column(Float, nullable=False)
    grant = Column(String)


class SourceGroupORM(Base):
    __tablename__ = "source_groups"

    id = Column(Integer, primary_key=True)
    source_group_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    grant = Column(String)

    sources = relationship(
        "SourceORM",
        back_populates="source_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SourceORM(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    ra = Column(Float, nullable=False)
    dec = Column(Float, nullable=False)
    extra = Column(JSON)
    source_group_id = Column(
        Integer, ForeignKey("source_groups.id", ondelete="CASCADE"), nullable=False
    )

    source_group = relationship("SourceGroupORM", back_populates="sources")
