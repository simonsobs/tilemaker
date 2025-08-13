from cachetools import LFUCache
from pymemcache.client.base import Client

from .core import AnalysisProvider, ProductNotFoundError
from .products import AnalysisProduct
from .types import AnalysisType


class InMemoryAnalysisCache(AnalysisProvider):
    """
    A simple in-memory cache for tiles.
    """

    cache: LFUCache

    def __init__(self, cache_size: int = 8192, internal_provider_id: str | None = None):
        self.cache = LFUCache(maxsize=cache_size)
        super().__init__(internal_provider_id=internal_provider_id)

    def pull(self, analysis_id: str, grants: set[str]):
        log = self.logger.bind(analysis_id=analysis_id)

        cached = self.cache.get(analysis_id, None)

        if cached is None:
            log.debug("analysis.inmemory.miss")
            raise ProductNotFoundError(f"Product {analysis_id} not found in cache")

        if cached.grant and cached.grant not in grants:
            log = log.bind(product_grant=cached.grant, user_grants=grants)
            log.debug("analysis.inmemory.proprietary_hidden")
            raise ProductNotFoundError(f"Product {analysis_id} not found in cache")

        log.debug("analysis.inmemory.pulled")
        return cached

    def push(self, product: AnalysisType):
        log = self.logger.bind(analysis_id=product.hash)

        if product.source == self.internal_provider_id:
            log.debug("analysis.inmemory.present")

        product.source = self.internal_provider_id
        self.cache[product.hash] = product
        log.debug("analysis.inmemory.pushed")


class MemcachedAnalysisCache(AnalysisProvider):
    """
    A cache that uses Memcached for storing tiles.
    """

    client: Client

    def __init__(self, client: Client, internal_provider_id: str | None = None):
        self.client = client
        super().__init__(
            internal_provider_id=internal_provider_id or "memcached-analysis"
        )

    def pull(self, analysis_id: str, grants: set[str]):
        log = self.logger.bind(analysis_id=analysis_id)

        res = self.client.get(analysis_id, None)

        if res is None:
            log.debug("analysis.memcached.miss")
            raise ProductNotFoundError(f"Product {analysis_id} not found in cache")

        res = AnalysisType.model_validate_json(res)

        if res.grant and res.grant not in grants:
            log = log.bind(product_grant=res.grant, user_grants=grants)
            log.debug("analysis.memcached.proprietary_hidden")
            raise ProductNotFoundError(f"Product {analysis_id} not found in cache")

        log.debug("analysis.memcached.pulled")

        return res

    def push(self, product: AnalysisProduct):
        log = self.logger.bind(analysis_id=product.hash)

        if product.source == self.internal_provider_id:
            log.debug("analysis.memcached.present")

        product.source = self.internal_provider_id
        self.client.set(product.hash, product.model_dump_json(), noreply=True)
        log.debug("analysis.memcached.pushed")
