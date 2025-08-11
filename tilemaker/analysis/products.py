from abc import ABC, abstractmethod

from pydantic import BaseModel


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
    def build(cls, tiles: "Tiles", metadata: list["MapGroup"], layer_id: str):
        return
