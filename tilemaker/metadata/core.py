import itertools
from pathlib import Path
from typing import Iterable

import structlog
from pydantic import BaseModel

from .boxes import Box
from .definitions import Layer, MapGroup
from .sources import SourceGroup


class DataConfiguration(BaseModel):
    map_groups: list[MapGroup] = []
    boxes: list[Box] = []
    source_groups: list[SourceGroup] = []

    def merge(self, other: "DataConfiguration") -> "DataConfiguration":
        return DataConfiguration(
            map_groups=self.map_groups + other.map_groups,
            boxes=self.boxes + other.boxes,
            source_groups=self.source_groups + other.source_groups,
        )

    @property
    def layers(self) -> Iterable[Layer]:
        return itertools.chain.from_iterable(
            band.layers
            for group in self.map_groups
            for map in group.maps
            for band in map.bands
        )

    def layer(self, layer_id: str) -> Layer | None:
        for x in self.layers:
            if x.layer_id == layer_id:
                return x

        return None

    def source_group(self, source_group_id: str) -> SourceGroup | None:
        for x in self.source_groups:
            if source_group_id == x.source_group_id:
                return x

        return None


def parse_config(config: Path) -> DataConfiguration:
    log = structlog.get_logger()
    log = log.bind(config_path=str(config))

    with open(config, "r") as handle:
        mgl = DataConfiguration.model_validate_json(handle.read())

    log = log.bind(
        map_groups=len(mgl.map_groups),
        boxes=len(mgl.boxes),
        source_groups=len(mgl.source_groups),
    )
    log.info("config.parsed")

    return mgl
