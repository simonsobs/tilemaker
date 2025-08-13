from abc import ABC, abstractmethod

from pydantic import BaseModel

from tilemaker.metadata.core import DataConfiguration
from tilemaker.providers.core import Tiles


class AnalysisProduct(BaseModel, ABC):
    layer_id: str
    grant: str | None
    source: str | None = None

    @property
    @abstractmethod
    def hash(self):
        return

    @classmethod
    @abstractmethod
    def build(cls, tiles: "Tiles", metadata: DataConfiguration, layer_id: str):
        return
