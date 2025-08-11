"""
Analysis caching and producing services.
"""

import uuid
from abc import ABC, abstractmethod

import structlog
from structlog.types import FilteringBoundLogger

from tilemaker.analysis.products import AnalysisProduct
from tilemaker.metadata.core import DataConfiguration
from tilemaker.providers.core import Tiles

from .types import SLUG_TO_TYPE


class ProductNotFoundError(Exception):
    pass


class AnalysisProvider(ABC):
    internal_provider_id: str
    logger: FilteringBoundLogger

    def __init__(self, internal_provider_id: str | None):
        self.internal_provider_id = internal_provider_id or str(uuid.uuid4())
        self.logger = structlog.get_logger()

    @abstractmethod
    def pull(self, analysis_id: str, grants: set[str]):
        return

    @abstractmethod
    def push(self, product: "AnalysisProduct"):
        return


class Analyses:
    pullable: list[AnalysisProvider]
    pushable: list[AnalysisProvider]
    tiles: Tiles
    metadata: DataConfiguration

    def __init__(
        self,
        pullable: list[AnalysisProvider],
        pushable: list[AnalysisProvider],
        tiles: Tiles,
        metadata: DataConfiguration,
    ):
        self.pullable = pullable
        self.pushable = pushable
        self.tiles = tiles
        self.metadata = metadata

    def pull(self, analysis_id: str, grants: set[str]) -> "AnalysisProduct":
        for provider in self.pullable:
            try:
                product = provider.pull(analysis_id=analysis_id, grants=grants)

                if product.grant and product.grant not in grants:
                    raise ProductNotFoundError(f"Product {analysis_id} not found")
            except ProductNotFoundError:
                continue

        # We couldn't find it. Try building it?
        for slug, analysis_type in SLUG_TO_TYPE.items():
            if slug in analysis_id:
                product = analysis_type.build(
                    tiles=self.tiles, metadata=self.metadata, analysis_id=analysis_id
                )

                self.push(product)

            if product.grant and product.grant not in grants:
                raise ProductNotFoundError(f"Product {analysis_id} not found")

        return product

    def push(self, product: "AnalysisProduct"):
        for provider in self.pushable:
            provider.push(product)

        return
