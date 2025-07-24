"""
Caches for tiles.
"""

import abc

import numpy as np
import structlog
from cachetools import LFUCache
from pymemcache.client.base import Client


class TileNotFound(Exception):
    """Raised when a tile is not found in the cache."""

    pass


class TileCache(abc.ABC):
    @abc.abstractmethod
    def get_cache(
        self, band: int, x: int, y: int, level: int, proprietary: bool
    ) -> np.ndarray | None:
        raise NotImplementedError

    @abc.abstractmethod
    def set_cache(
        self,
        band: int,
        x: int,
        y: int,
        level: int,
        data: np.ndarray | None,
        proprietary: bool,
    ) -> None:
        raise NotImplementedError


class PassThroughCache(TileCache):
    def get_cache(
        self, band: int, x: int, y: int, level: int, proprietary: bool
    ) -> np.ndarray | None:
        """
        A cache that does nothing. It is used when caching is disabled.
        """
        raise TileNotFound(f"Tile {band}-{level}-{x}-{y} not found in cache.")

    def set_cache(
        self,
        band: int,
        x: int,
        y: int,
        level: int,
        data: np.ndarray | None,
        proprietary: bool,
    ) -> None:
        """
        A cache that does nothing. It is used when caching is disabled.
        """
        pass


class InMemoryCache(TileCache):
    """
    A simple in-memory cache for tiles.
    """

    def __init__(self, cache_size: int = 8192):
        self.proprietary_cache = LFUCache(maxsize=cache_size)
        self.public_cache = LFUCache(maxsize=cache_size)

    def get_cache(
        self, band: int, x: int, y: int, level: int, proprietary: bool
    ) -> np.ndarray | None:
        tile_hash = f"{band}-{level}-{x}-{y}"
        if proprietary:
            if tile_hash in self.proprietary_cache:
                return self.proprietary_cache.get(tile_hash)

        if tile_hash in self.public_cache:
            return self.public_cache.get(tile_hash)

        raise TileNotFound(f"Tile {band}-{level}-{x}-{y} not found in cache.")

    def set_cache(
        self,
        band: int,
        x: int,
        y: int,
        level: int,
        data: np.ndarray | None,
        proprietary: bool,
    ) -> None:
        tile_hash = f"{band}-{level}-{x}-{y}"
        if proprietary:
            self.proprietary_cache[tile_hash] = data
        else:
            self.public_cache[tile_hash] = data


class MemcachedCache(TileCache):
    """
    A cache that uses Memcached for storing tiles.
    """

    def __init__(self, client: Client):
        self.client = client

    def get_cache(
        self, band: int, x: int, y: int, level: int, proprietary: bool
    ) -> np.ndarray | None:
        tile_hash = f"{band}-{level}-{x}-{y}"
        log = structlog.get_logger()
        log = log.bind(tile_hash=tile_hash)
        res = self.client.get(tile_hash, None)

        if res is None:
            log.debug("memcached.miss")
            raise TileNotFound(f"Tile {tile_hash} not found in cache.")

        prop, data = res

        if prop and not proprietary:
            log = log.debug("memcached.proprietary_hidden")
            return None

        log.debug("memcached.read")
        return data

    def set_cache(
        self,
        band: int,
        x: int,
        y: int,
        level: int,
        data: np.ndarray | None,
        proprietary: bool,
    ) -> None:
        tile_hash = f"{band}-{level}-{x}-{y}"
        log = structlog.get_logger()
        log = log.bind(tile_hash=tile_hash, proprietary=proprietary)
        log.debug("memcached.set")
        self.client.set(tile_hash, (proprietary, data), noreply=True)
