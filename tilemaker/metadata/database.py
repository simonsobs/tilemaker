"""
A database-backed implementation of the DataConfiguration object. Used in produciton
when you need to be able to dynamically update the available maps. Comes along
with tools to populate the database from a static configuration file and delete
entries as needed.
"""

import itertools
from typing import Iterable

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .boxes import Box
from .core import DataConfiguration
from .definitions import (
    Band,
    Layer,
    Map,
    MapGroup,
)
from .fits import FITSLayerProvider
from .orm import (
    BandORM,
    Base,
    BoxORM,
    LayerORM,
    MapGroupORM,
    MapORM,
    SourceGroupORM,
    SourceORM,
)
from .sources import Source, SourceGroup


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

    # Deletion methods
    def delete_layer(self, layer_id: str) -> bool:
        """Delete a layer by its ID."""
        with self.session_maker() as session:
            orm_layer = session.query(LayerORM).filter_by(layer_id=layer_id).first()
            if orm_layer is None:
                return False
            session.delete(orm_layer)
            session.commit()
            return True

    def delete_band(self, band_id: str, map_id: str | None = None) -> bool:
        """Delete a band by band_id (optionally scoping by map_id to disambiguate)."""
        with self.session_maker() as session:
            query = session.query(BandORM).filter_by(band_id=band_id)
            if map_id is not None:
                query = query.join(MapORM).filter(MapORM.map_id == map_id)
            orm_band = query.first()
            if orm_band is None:
                return False
            session.delete(orm_band)
            session.commit()
            return True

    def delete_map(self, map_id: str) -> bool:
        """Delete a map by its map_id."""
        with self.session_maker() as session:
            orm_map = session.query(MapORM).filter_by(map_id=map_id).first()
            if orm_map is None:
                return False
            session.delete(orm_map)
            session.commit()
            return True

    def delete_map_group(self, name: str) -> bool:
        """Delete a map group by its name."""
        with self.session_maker() as session:
            orm_group = session.query(MapGroupORM).filter_by(name=name).first()
            if orm_group is None:
                return False
            session.delete(orm_group)
            session.commit()
            return True

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
            # Populate map groups, maps, bands, and layers without duplicating existing rows
            for map_group in config.map_groups:
                orm_group = (
                    session.query(MapGroupORM).filter_by(name=map_group.name).first()
                )
                if orm_group is None:
                    orm_group = MapGroupORM(
                        name=map_group.name,
                        description=map_group.description,
                        grant=map_group.grant,
                    )
                    session.add(orm_group)
                    session.flush()
                else:
                    orm_group.description = map_group.description
                    orm_group.grant = map_group.grant
                    session.flush()

                for map in map_group.maps:
                    orm_map = session.query(MapORM).filter_by(map_id=map.map_id).first()
                    if orm_map is None:
                        orm_map = MapORM(
                            map_id=map.map_id,
                            name=map.name,
                            description=map.description,
                            grant=map.grant,
                            map_group_id=orm_group.id,
                        )
                        session.add(orm_map)
                        session.flush()
                    else:
                        orm_map.name = map.name
                        orm_map.description = map.description
                        orm_map.grant = map.grant
                        orm_map.map_group_id = orm_group.id
                        session.flush()

                    for band in map.bands:
                        orm_band = (
                            session.query(BandORM)
                            .filter(
                                BandORM.band_id == band.band_id,
                                BandORM.map_id == orm_map.id,
                            )
                            .first()
                        )

                        if orm_band is None:
                            orm_band = BandORM(
                                band_id=band.band_id,
                                name=band.name,
                                description=band.description,
                                grant=band.grant,
                                map_id=orm_map.id,
                            )
                            session.add(orm_band)
                            session.flush()
                        else:
                            orm_band.name = band.name
                            orm_band.description = band.description
                            orm_band.grant = band.grant
                            orm_band.map_id = orm_map.id
                            session.flush()

                        for layer in band.layers:
                            provider_adapter = TypeAdapter(type(layer.provider))
                            provider_dict = provider_adapter.dump_python(
                                layer.provider, mode="json"
                            )

                            vmin_str = None if layer.vmin is None else str(layer.vmin)
                            vmax_str = None if layer.vmax is None else str(layer.vmax)

                            orm_layer = (
                                session.query(LayerORM)
                                .filter_by(layer_id=layer.layer_id)
                                .first()
                            )

                            if orm_layer is None:
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
                            else:
                                orm_layer.name = layer.name
                                orm_layer.description = layer.description
                                orm_layer.grant = layer.grant
                                orm_layer.band_id = orm_band.id
                                orm_layer.quantity = layer.quantity
                                orm_layer.units = layer.units
                                orm_layer.number_of_levels = layer.number_of_levels
                                orm_layer.tile_size = layer.tile_size
                                orm_layer.vmin = vmin_str
                                orm_layer.vmax = vmax_str
                                orm_layer.cmap = layer.cmap
                                orm_layer.provider = provider_dict
                                orm_layer.bounding_left = layer.bounding_left
                                orm_layer.bounding_right = layer.bounding_right
                                orm_layer.bounding_top = layer.bounding_top
                                orm_layer.bounding_bottom = layer.bounding_bottom

            # Populate boxes without duplicates (keyed by name)
            for box in config.boxes:
                orm_box = session.query(BoxORM).filter_by(name=box.name).first()
                if orm_box is None:
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
                else:
                    orm_box.description = box.description
                    orm_box.top_left_ra = box.top_left_ra
                    orm_box.top_left_dec = box.top_left_dec
                    orm_box.bottom_right_ra = box.bottom_right_ra
                    orm_box.bottom_right_dec = box.bottom_right_dec
                    orm_box.grant = box.grant

            # Populate source groups and sources without duplicates
            for source_group in config.source_groups:
                orm_source_group = (
                    session.query(SourceGroupORM)
                    .filter_by(source_group_id=source_group.source_group_id)
                    .first()
                )

                if orm_source_group is None:
                    orm_source_group = SourceGroupORM(
                        source_group_id=source_group.source_group_id,
                        name=source_group.name,
                        description=source_group.description,
                        grant=source_group.grant,
                    )
                    session.add(orm_source_group)
                    session.flush()
                else:
                    orm_source_group.name = source_group.name
                    orm_source_group.description = source_group.description
                    orm_source_group.grant = source_group.grant
                    session.flush()

                # Replace sources for this group to avoid duplication
                session.query(SourceORM).filter_by(
                    source_group_id=orm_source_group.id
                ).delete(synchronize_session=False)

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


def main():
    """
    Run the CLI wrapper to help with managing the databases. There are a number of
    commands:

    tilemaker-db {group,map,layer,band,source_group,box,source} delete <id>
        Delete an entry from the database by its ID.

    tilemaker-db {group,map,layer,band,source_group,box,source} list
        List all entries of a given type in the database.

    tilemaker-db populate <config.json>
        Populate the database from a static configuration file.

    tilemaker-db details
        Show summary details about the database contents.

    Note that the database configuration details are as specified in your
    tilemaker central configuration.
    """
    import argparse as ap
    from pathlib import Path

    from tilemaker.settings import settings

    database_configuration = settings.parse_config()

    if not isinstance(database_configuration, DatabaseDataConfiguration):
        print(
            "This CLI only works with database-backed configurations loaded via settings."
        )
        return

    parser = ap.ArgumentParser(description="Tilemaker database management CLI")

    subparsers = parser.add_subparsers(dest="command", required=True)

    populate_parser = subparsers.add_parser(
        "populate", help="Populate the database from a static config JSON file"
    )
    populate_parser.add_argument(
        "config",
        help="Path to the JSON configuration file (same schema as static config)",
    )

    list_parser = subparsers.add_parser("list", help="List entries of a given type")
    list_parser.add_argument(
        "entity",
        choices=["group", "map", "band", "layer", "box", "source_group", "source"],
    )

    bands_parser = subparsers.add_parser(
        "bands", help="List all bands for a specific map"
    )
    bands_parser.add_argument("map_id", help="The map ID")

    layers_parser = subparsers.add_parser(
        "layers", help="List all layers for a specific map"
    )
    layers_parser.add_argument("map_id", help="The map ID")

    delete_parser = subparsers.add_parser(
        "delete", help="Delete an entry of a given type by identifier"
    )
    delete_parser.add_argument(
        "entity",
        choices=["group", "map", "band", "layer", "source_group"],
        help="Entity type to delete. Boxes/sources require manual handling.",
    )
    delete_parser.add_argument("identifier", help="Identifier (e.g., layer_id, map_id)")
    delete_parser.add_argument(
        "--map-id",
        help="Map ID to disambiguate band deletes (optional)",
    )

    subparsers.add_parser(
        "details", help="Show summary details about the database contents"
    )

    args = parser.parse_args()

    if args.command == "populate":
        database_configuration.create_tables()
        # Load static config file as DataConfiguration for ingestion
        cfg_json = Path(args.config).read_text()
        ingest_cfg = DataConfiguration.model_validate_json(cfg_json)
        database_configuration.populate_from_config(ingest_cfg)
        print("Database populated from config")
        return

    if args.command == "list":
        if args.entity == "group":
            for g in database_configuration.map_groups:
                print(g.name)
        elif args.entity == "map":
            for g in database_configuration.map_groups:
                for m in g.maps:
                    print(m.map_id, m.name)
        elif args.entity == "band":
            for g in database_configuration.map_groups:
                for m in g.maps:
                    for b in m.bands:
                        print(b.band_id, b.name)
        elif args.entity == "layer":
            for layer in database_configuration.layers:
                print(layer.layer_id, layer.name)
        elif args.entity == "box":
            for b in database_configuration.boxes:
                print(b.name)
        elif args.entity == "source_group":
            for sg in database_configuration.source_groups:
                print(sg.source_group_id)
        elif args.entity == "source":
            for sg in database_configuration.source_groups:
                if sg.sources:
                    for s in sg.sources:
                        print(f"{sg.source_group_id}:{s.name}")
        return

    if args.command == "bands":
        found = False
        for g in database_configuration.map_groups:
            for m in g.maps:
                if m.map_id == args.map_id:
                    found = True
                    for b in m.bands:
                        print(b.band_id, b.name)
        if not found:
            print(f"Map {args.map_id} not found")
        return

    if args.command == "layers":
        found = False
        for g in database_configuration.map_groups:
            for m in g.maps:
                if m.map_id == args.map_id:
                    found = True
                    for b in m.bands:
                        for layer in b.layers:
                            print(layer.layer_id, layer.name)
        if not found:
            print(f"Map {args.map_id} not found")

    if args.command == "delete":
        ok = False
        if args.entity == "layer":
            ok = database_configuration.delete_layer(args.identifier)
        elif args.entity == "band":
            ok = database_configuration.delete_band(args.identifier, map_id=args.map_id)
        elif args.entity == "map":
            ok = database_configuration.delete_map(args.identifier)
        elif args.entity == "group":
            ok = database_configuration.delete_map_group(args.identifier)
        elif args.entity == "source_group":
            with database_configuration.session_maker() as session:
                orm_sg = (
                    session.query(SourceGroupORM)
                    .filter_by(source_group_id=args.identifier)
                    .first()
                )
                if orm_sg:
                    session.delete(orm_sg)
                    session.commit()
                    ok = True
        if ok:
            print("Deleted", args.entity, args.identifier)
        else:
            print(args.entity, args.identifier, "not found")
        return

    if args.command == "details":
        print(f"Map groups: {len(database_configuration.map_groups)}")
        print(f"Maps: {sum(len(g.maps) for g in database_configuration.map_groups)}")
        print(f"Layers: {sum(1 for _ in database_configuration.layers)}")
        print(f"Boxes: {len(database_configuration.boxes)}")
        sg = database_configuration.source_groups
        print(f"Source groups: {len(sg)}")
        print(f"Sources: {sum(len(x.sources or []) for x in sg)}")
        return
