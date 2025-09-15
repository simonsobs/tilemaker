"""
Caches for tiles.
"""

from cachetools import LFUCache
from pymemcache.client.base import Client

from .core import PullableTile, PushableTile, TileNotFoundError, TileProvider


class PassThroughCache(TileProvider):
    def pull(self, tile: PullableTile):
        """
        A cache that does nothing. It is used when caching is disabled.
        """
        log = self.logger.bind(tile_hash=tile.hash)
        log.info("passthrough.pull")
        raise TileNotFoundError

    def push(self, tile: PushableTile):
        """
        A cache that does nothing. It is used when caching is disabled.
        """
        log = self.logger.bind(tile_hash=tile.hash)
        log.info("passthrough.push")
        pass


class InMemoryCache(TileProvider):
    """
    A simple in-memory cache for tiles.
    """

    cache: LFUCache

    def __init__(self, cache_size: int = 8192, internal_provider_id: str | None = None):
        self.cache = LFUCache(maxsize=cache_size)
        super().__init__(internal_provider_id=internal_provider_id)

    def pull(self, tile: PullableTile):
        log = self.logger.bind(tile_hash=tile.hash)

        cached = self.cache.get(tile.hash, None)

        if cached is None:
            log.debug("provider.inmemory.miss")
            raise TileNotFoundError(f"Tile {tile.hash} not found in cache")

        if cached.grant and cached.grant != tile.grant:
            log = log.bind(tile_grant=cached.grant, user_grant=tile.grant)
            log.debug("provider.inmemory.proprietary_hidden")
            raise TileNotFoundError(f"Tile {tile.hash} not found in cache")

        log.debug("provider.inmemory.pulled")
        return cached

    def push(self, tile: PushableTile):
        log = self.logger.bind(tile_hash=tile.hash)

        if tile.source == self.internal_provider_id:
            log.debug("provider.inmemory.present")
            return

        tile.source = self.internal_provider_id
        self.cache[tile.hash] = tile
        log.debug("provider.inmemory.pushed")


class MemcachedCache(TileProvider):
    """
    A cache that uses Memcached for storing tiles.
    """

    client: Client

    def __init__(self, client: Client, internal_provider_id: str | None = None):
        self.client = client
        super().__init__(internal_provider_id=internal_provider_id or "memcached")

    def pull(self, tile: PullableTile):
        log = self.logger.bind(tile_hash=tile.hash)

        res = self.client.get(tile.hash, None)

        if res is None:
            log.debug("provider.memcached.miss")
            raise TileNotFoundError(f"Tile {tile.hash} not found in cache")

        grant, data = res

        if grant and grant not in tile.grants:
            log = log.bind(tile_grant=grant, user_grant=tile.grants)
            log.debug("provider.memcached.proprietary_hidden")
            raise TileNotFoundError(f"Tile {tile.hash} not found in cache")

        log.debug("provider.memcached.pulled")

        return PushableTile(
            layer_id=tile.layer_id,
            x=tile.x,
            y=tile.y,
            level=tile.y,
            grant=grant,
            data=data,
            source=self.internal_provider_id,
        )

    def push(self, tile: PushableTile):
        log = self.logger.bind(tile_hash=tile.hash)

        if tile.source == self.internal_provider_id:
            log.debug("provider.memcached.present")
            return

        tile.source = self.internal_provider_id
        self.client.set(tile.hash, (tile.grant, tile.data), noreply=True)
        log.debug("provider.memcached.pushed")
