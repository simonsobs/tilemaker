"""
Settings for the project.
"""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    config_path: Path = "config.json"

    origins: list[str] | None = ["*"]
    add_cors: bool = True
    "Settings for managng CORS middleware; useful for development."

    serve_frontend: bool = True
    "Whether to serve the frontend. If False, the frontend must be served elsewhere; useful for large deployments or development."

    api_endpoint: str = "./"
    "The location of the API endpoint. Default assumes from the same place as the server."

    auth_type: Literal["soauth", "mock"] = "mock"
    "The authentication type to use."

    # SOAuth settings (if used)
    soauth_base_url: str | None = None
    soauth_auth_url: str | None = None
    soauth_app_id: str | None = None
    soauth_client_secret: str | None = None
    soauth_public_key: str | None = None
    soauth_key_pair_type: str | None = None

    # Caching settings
    cache_type: Literal["in_memory", "memcached", "pass_through"] = "in_memory"
    "Type of caching to use for tiles. Options are 'in_memory', 'memcached', or 'pass_through'."
    memcached_host: str = "localhost"
    "Host for the Memcached server."
    memcached_port: int = 11211
    "Port for the Memcached server."
    memcached_client_pool_size: int = 4
    "Number of connections in the Memcached client pool."
    memcached_timeout_seconds: float = 0.5
    "Timeout for Memcached operations in seconds."
    precache: bool = True
    "Whether or not to pre-cache the histogram for every layer. This will also pre-cache the first layer of tiles."

    class Config:
        env_prefix = "TILEMAKER_"

    def create_cache(self) -> list:
        """
        Create a cache instance based on the settings.
        """
        if self.cache_type == "in_memory":
            from tilemaker.providers.caching import InMemoryCache

            return [InMemoryCache()]
        elif self.cache_type == "memcached":
            from pymemcache import serde
            from pymemcache.client.base import PooledClient

            from tilemaker.providers.caching import MemcachedCache

            client = PooledClient(
                server=(self.memcached_host, self.memcached_port),
                serde=serde.pickle_serde,
                max_pool_size=self.memcached_client_pool_size,
                timeout=self.memcached_timeout_seconds,
                ignore_exc=True,
            )
            return [MemcachedCache(client=client)]
        else:
            return []

    def create_analysis_cache(self) -> list:
        """
        Create a cache instance based on the settings.
        """
        if self.cache_type == "in_memory":
            from tilemaker.analysis.providers import InMemoryAnalysisCache

            return [InMemoryAnalysisCache()]
        elif self.cache_type == "memcached":
            from pymemcache import serde
            from pymemcache.client.base import PooledClient

            from tilemaker.analysis.providers import MemcachedAnalysisCache

            client = PooledClient(
                server=(self.memcached_host, self.memcached_port),
                serde=serde.pickle_serde,
                max_pool_size=self.memcached_client_pool_size,
                timeout=self.memcached_timeout_seconds,
                ignore_exc=True,
            )
            return [MemcachedAnalysisCache(client=client)]
        else:
            return []

    def setup_app(self, app: FastAPI):
        from tilemaker.analysis.core import Analyses
        from tilemaker.providers.core import Tiles
        from tilemaker.providers.fits import FITSTileProvider

        if not hasattr(app, "config"):
            app.config = settings.parse_config()

        cache = self.create_cache()

        tp = FITSTileProvider(map_groups=app.config.map_groups)
        app.tiles = Tiles(pullable=cache + [tp], pushable=cache)

        cache = self.create_analysis_cache()
        app.analyses = Analyses(
            pullable=cache, pushable=cache, tiles=app.tiles, metadata=app.config
        )

        if self.precache:
            for layer in app.config.layers:
                app.analyses.pull(
                    f"hist-{layer.layer_id}",
                    grants={layer.grant} if layer.grant is not None else None,
                )

        return app

    def parse_config(self):
        from tilemaker.metadata.core import parse_config

        return parse_config(self.config_path)


settings = Settings()
