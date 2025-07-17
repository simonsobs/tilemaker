"""
Settings for the project.
"""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./tilemaker.db"
    "SQLAlchemy-appropriate database URL."

    origins: list[str] | None = ["*"]
    add_cors: bool = True
    "Settings for managng CORS middleware; useful for development."

    serve_frontend: bool = True
    "Whether to serve the frontend. If False, the frontend must be served elsewhere; useful for large deployments or development."

    api_endpoint: str = "./"
    "The location of the API endpoint. Default assumes from the same place as the server."

    use_in_memory_cache: bool = True
    "Use an in-memory cache for the tiles. Can improve performance by reducing database queries."

    proprietary_scope: str = "simonsobs"
    "The scope to require for proprietary data access."

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
    memcached_client_pool_size: int = 16
    "Number of connections in the Memcached client pool."
    memcached_timeout_seconds: float = 0.5
    "Timeout for Memcached operations in seconds."

    class Config:
        env_prefix = "TILEMAKER_"

    def create_cache(self):
        """
        Create a cache instance based on the settings.
        """
        if self.cache_type == "in_memory":
            from tilemaker.server.caching import InMemoryCache

            return InMemoryCache()
        elif self.cache_type == "memcached":
            from pymemcache import serde
            from pymemcache.client.base import PooledClient

            from tilemaker.server.caching import MemcachedCache

            client = PooledClient(
                server=(self.memcached_host, self.memcached_port),
                serde=serde.pickle_serde,
                max_pool_size=self.memcached_client_pool_size,
                timeout=self.memcached_timeout_seconds,
                ignore_exc=True,
            )
            return MemcachedCache(client=client)
        else:
            from tilemaker.server.caching import PassThroughCache

            return PassThroughCache()


settings = Settings()
