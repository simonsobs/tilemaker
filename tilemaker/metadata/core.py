import itertools
from pathlib import Path
from typing import Iterable

import structlog
from pydantic import BaseModel

from .boxes import Box
from .definitions import Band, Layer, LayerWithMenuState, MapGroup, SearchResponse
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

    def _match(self, name: str, query: str) -> bool:
        return query.lower() in name.lower()

    def filter_map_groups(
        self, authorized_map_groups: list, query: str
    ) -> SearchResponse:
        matched_ids: set[str] = set()
        filtered_groups = []

        for group in authorized_map_groups:
            # Group name matches — keep entire subtree intact
            if self._match(group["name"], query):
                matched_ids.add(group["map_group_id"])
                filtered_groups.append(group)
                continue

            filtered_maps = []
            for map in group.get("maps", []):
                # Map name matches — keep entire subtree intact
                if self._match(map["name"], query):
                    matched_ids.add(map["map_id"])
                    filtered_maps.append(map)
                    continue

                filtered_bands = []
                for band in map.get("bands", []):
                    # Band name matches — keep entire subtree intact
                    if self._match(band["name"], query):
                        matched_ids.add(band["band_id"])
                        filtered_bands.append(band)
                        continue

                    filtered_layers = [
                        layer
                        for layer in band.get("layers", [])
                        if self._match(layer["name"], query)
                        and matched_ids.add(layer["layer_id"]) is None
                    ]
                    if filtered_layers:
                        filtered_bands.append({**band, "layers": filtered_layers})

                if filtered_bands:
                    filtered_maps.append({**map, "bands": filtered_bands})

            if filtered_maps:
                filtered_groups.append({**group, "maps": filtered_maps})

        return SearchResponse(
            filtered_layer_menu=filtered_groups,
            matched_ids=list(matched_ids),
        )

    @property
    def bands(self) -> Iterable[Band]:
        return itertools.chain.from_iterable(
            map.bands for group in self.map_groups for map in group.maps
        )

    @property
    def layers(self) -> Iterable[LayerWithMenuState]:
        return (
            LayerWithMenuState(
                **layer.model_dump(),
                map_group_id=group.map_group_id,
                map_id=map.map_id,
                band_id=band.band_id,
            )
            for group in self.map_groups
            for map in group.maps
            for band in map.bands
            for layer in band.layers
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
