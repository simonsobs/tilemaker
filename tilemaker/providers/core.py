"""
Core (abstract) tile provider.
"""

from pydantic import BaseModel
from abc import ABC, abstractmethod
import uuid
import numpydantic
import structlog
from structlog.types import FilteringBoundLogger


class TileNotFoundError(Exception):
    pass

class PullableTile(BaseModel):
    band_id: int
    x: int
    y: int
    level: int
    grant: str | None

    @property
    def hash(self) -> str:
        return f"{self.band_id}-{self.x}-{self.y}-{self.level}"

class PushableTile(BaseModel):
    band_id: int
    x: int
    y: int
    level: int
    grant: str | None
    data: numpydantic.NDArray | None
    source: str

    @property
    def hash(self) -> str:
        return f"{self.band_id}-{self.x}-{self.y}-{self.level}"

class TileProvider(ABC):
    internal_provider_id: str
    logger: FilteringBoundLogger
    def __init__(self, internal_provider_id: str | None):
        self.internal_provider_id = internal_provider_id or str(uuid.uuid4()) 
        self.logger = structlog.get_logger()

    @abstractmethod
    def pull(self, tile: PullableTile) -> PushableTile:
        raise NotImplementedError
    
    @abstractmethod
    def push(self, tile: PushableTile):
        raise NotImplementedError
    

class Tiles:
    pullable: list[TileProvider]
    pushable: list[TileProvider]

    def __init__(self, pullable: list[TileProvider], pushable: list[TileProvider]):
        self.pullable = pullable
        self.pushable = pushable


    def pull(self, tile: PullableTile) -> tuple[PushableTile, list[PushableTile]]:
        data = None
        pushables = []
        for provider in self.pullable:
            try:
                data = provider.pull(tile)
                pushables.append(data)
                break
            except TileNotFoundError:
                continue
        
        if not data:
            # TODO: Recurse and find the 'lower' tiles, combine them?
            raise TileNotFoundError

        return data, pushables
    
    def push(self, tiles: list[PushableTile]):
        for provider in self.pushable:
            for tile in tiles:
                provider.push(tile)

        return





