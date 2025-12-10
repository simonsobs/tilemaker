"""
A database-backed implementation of the DataConfiguration object.
"""

import itertools
from typing import Iterable

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .boxes import Box
from .definitions import (
    Band,
    Layer,
    Map,
    MapGroup,
)
from .fits import FITSLayerProvider
from .orm import (
    Base,
    BandORM,
    BoxORM,
    LayerORM,
    MapGroupORM,
    MapORM,
    SourceGroupORM,
    SourceORM,
)
from .sources import Source, SourceGroup
from .core import DataConfiguration


class DatabaseDataConfiguration:
    """
    A database-backed implementation of the DataConfiguration object using SQLAlchemy.
    """

    def __init__(self, database_url: str):
        """
        Initialize the database configuration.

        Parameters
        ----------
        database_url : str
            SQLAlchemy database URL (e.g., 'sqlite:///config.db', 'postgresql://user:password@localhost/dbname')
        """
        self.engine = create_engine(database_url)
        self.session_maker = sessionmaker(bind=self.engine)
        self.log = structlog.get_logger()

    def create_tables(self):
        """Create all tables in the database."""
        Base.metadata.create_all(self.engine)

    @property
    def map_groups(self) -> list[MapGroup]:
        """Retrieve all map groups from the database."""
        with self.session_maker() as session:
            orm_groups = session.query(MapGroupORM).all()
            return [
                self._orm_to_map_group(session, orm_group) for orm_group in orm_groups
            ]

    @property
    def boxes(self) -> list[Box]:
        """Retrieve all boxes from the database."""
        with self.session_maker() as session:
            orm_boxes = session.query(BoxORM).all()
            return [self._orm_to_box(orm_box) for orm_box in orm_boxes]

    @property
    def source_groups(self) -> list[SourceGroup]:
        """Retrieve all source groups from the database."""
        with self.session_maker() as session:
            orm_groups = session.query(SourceGroupORM).all()
            return [
                self._orm_to_source_group(session, orm_group)
                for orm_group in orm_groups
            ]

    @property
    def layers(self) -> Iterable[Layer]:
        """Retrieve all layers from the database."""
        return itertools.chain.from_iterable(
            band.layers
            for group in self.map_groups
            for map in group.maps
            for band in map.bands
        )

    def layer(self, layer_id: str) -> Layer | None:
        """Retrieve a specific layer by its ID."""
        with self.session_maker() as session:
            orm_layer = session.query(LayerORM).filter_by(layer_id=layer_id).first()
            if orm_layer is None:
                return None
            return self._orm_to_layer(session, orm_layer)

    def source_group(self, source_group_id: str) -> SourceGroup | None:
        """Retrieve a specific source group by its ID."""
        with self.session_maker() as session:
            orm_group = (
                session.query(SourceGroupORM)
                .filter_by(source_group_id=source_group_id)
                .first()
            )
            if orm_group is None:
                return None
            return self._orm_to_source_group(session, orm_group)

    # Conversion methods
    def _orm_to_box(self, orm_box: BoxORM) -> Box:
        """Convert ORM Box to Pydantic Box."""
        return Box(
            name=orm_box.name,
            description=orm_box.description,
            top_left_ra=orm_box.top_left_ra,
            top_left_dec=orm_box.top_left_dec,
            bottom_right_ra=orm_box.bottom_right_ra,
            bottom_right_dec=orm_box.bottom_right_dec,
            grant=orm_box.grant,
        )

    def _orm_to_source(self, orm_source: SourceORM) -> Source:
        """Convert ORM Source to Pydantic Source."""
        return Source(
            name=orm_source.name,
            ra=orm_source.ra,
            dec=orm_source.dec,
            extra=orm_source.extra,
        )

    def _orm_to_source_group(
        self, session: Session, orm_group: SourceGroupORM
    ) -> SourceGroup:
        """Convert ORM SourceGroup to Pydantic SourceGroup."""
        sources = [self._orm_to_source(src) for src in orm_group.sources]
        return SourceGroup(
            source_group_id=orm_group.source_group_id,
            name=orm_group.name,
            description=orm_group.description,
            grant=orm_group.grant,
            sources=sources,
        )

    def _orm_to_layer(self, session: Session, orm_layer: LayerORM) -> Layer:
        """Convert ORM Layer to Pydantic Layer."""
        from pydantic import TypeAdapter

        # Deserialize provider from JSON using Pydantic
        provider_adapter = TypeAdapter(FITSLayerProvider)
        provider = provider_adapter.validate_python(orm_layer.provider)

        # Convert vmin/vmax from string storage to proper type
        vmin = orm_layer.vmin
        if vmin is not None and vmin != "auto":
            vmin = float(vmin)
        
        vmax = orm_layer.vmax
        if vmax is not None and vmax != "auto":
            vmax = float(vmax)

        return Layer(
            layer_id=orm_layer.layer_id,
            name=orm_layer.name,
            description=orm_layer.description,
            provider=provider,
            bounding_left=orm_layer.bounding_left,
            bounding_right=orm_layer.bounding_right,
            bounding_top=orm_layer.bounding_top,
            bounding_bottom=orm_layer.bounding_bottom,
            quantity=orm_layer.quantity,
            units=orm_layer.units,
            number_of_levels=orm_layer.number_of_levels,
            tile_size=orm_layer.tile_size,
            vmin=vmin,
            vmax=vmax,
            cmap=orm_layer.cmap,
            grant=orm_layer.grant,
        )

    def _orm_to_band(self, session: Session, orm_band: BandORM) -> Band:
        """Convert ORM Band to Pydantic Band."""
        layers = [self._orm_to_layer(session, layer) for layer in orm_band.layers]
        return Band(
            band_id=orm_band.band_id,
            name=orm_band.name,
            description=orm_band.description,
            layers=layers,
            grant=orm_band.grant,
        )

    def _orm_to_map(self, session: Session, orm_map: MapORM) -> Map:
        """Convert ORM Map to Pydantic Map."""
        bands = [self._orm_to_band(session, band) for band in orm_map.bands]
        return Map(
            map_id=orm_map.map_id,
            name=orm_map.name,
            description=orm_map.description,
            bands=bands,
            grant=orm_map.grant,
        )

    def _orm_to_map_group(self, session: Session, orm_group: MapGroupORM) -> MapGroup:
        """Convert ORM MapGroup to Pydantic MapGroup."""
        maps = [self._orm_to_map(session, map) for map in orm_group.maps]
        return MapGroup(
            name=orm_group.name,
            description=orm_group.description,
            maps=maps,
            grant=orm_group.grant,
        )

    def populate_from_config(self, config: "DataConfiguration") -> None:
        """
        Populate the database from a pre-existing DataConfiguration object.

        Parameters
        ----------
        config : DataConfiguration
            A DataConfiguration object (from core.py) containing map groups, boxes, and source groups.
        """
        from pydantic import TypeAdapter

        with self.session_maker() as session:
            # Populate map groups, maps, bands, and layers
            for map_group in config.map_groups:
                orm_group = MapGroupORM(
                    name=map_group.name,
                    description=map_group.description,
                    grant=map_group.grant,
                )
                session.add(orm_group)
                session.flush()  # Flush to get the group ID

                for map in map_group.maps:
                    orm_map = MapORM(
                        map_id=map.map_id,
                        name=map.name,
                        description=map.description,
                        grant=map.grant,
                        map_group_id=orm_group.id,
                    )
                    session.add(orm_map)
                    session.flush()

                    for band in map.bands:
                        orm_band = BandORM(
                            band_id=band.band_id,
                            name=band.name,
                            description=band.description,
                            grant=band.grant,
                            map_id=orm_map.id,
                        )
                        session.add(orm_band)
                        session.flush()

                        for layer in band.layers:
                            # Serialize provider to JSON
                            provider_adapter = TypeAdapter(type(layer.provider))
                            provider_dict = provider_adapter.dump_python(
                                layer.provider, mode="json"
                            )

                            # Convert vmin/vmax to string for storage
                            vmin_str = None if layer.vmin is None else str(layer.vmin)
                            vmax_str = None if layer.vmax is None else str(layer.vmax)

                            orm_layer = LayerORM(
                                layer_id=layer.layer_id,
                                name=layer.name,
                                description=layer.description,
                                grant=layer.grant,
                                band_id=orm_band.id,
                                quantity=layer.quantity,
                                units=layer.units,
                                number_of_levels=layer.number_of_levels,
                                tile_size=layer.tile_size,
                                vmin=vmin_str,
                                vmax=vmax_str,
                                cmap=layer.cmap,
                                provider=provider_dict,
                                bounding_left=layer.bounding_left,
                                bounding_right=layer.bounding_right,
                                bounding_top=layer.bounding_top,
                                bounding_bottom=layer.bounding_bottom,
                            )
                            session.add(orm_layer)

            # Populate boxes
            for box in config.boxes:
                orm_box = BoxORM(
                    name=box.name,
                    description=box.description,
                    top_left_ra=box.top_left_ra,
                    top_left_dec=box.top_left_dec,
                    bottom_right_ra=box.bottom_right_ra,
                    bottom_right_dec=box.bottom_right_dec,
                    grant=box.grant,
                )
                session.add(orm_box)

            # Populate source groups and sources
            for source_group in config.source_groups:
                orm_source_group = SourceGroupORM(
                    source_group_id=source_group.source_group_id,
                    name=source_group.name,
                    description=source_group.description,
                    grant=source_group.grant,
                )
                session.add(orm_source_group)
                session.flush()

                if source_group.sources:
                    for source in source_group.sources:
                        orm_source = SourceORM(
                            name=source.name,
                            ra=source.ra,
                            dec=source.dec,
                            extra=source.extra,
                            source_group_id=orm_source_group.id,
                        )
                        session.add(orm_source)

            session.commit()
            self.log.info("database.populated_from_config")
