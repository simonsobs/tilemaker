"""
Authentication setup.
"""

from fastapi import FastAPI, Request
from soauth.toolkit.fastapi import global_setup, mock_global_setup
from sqlalchemy import Select

from ..settings import settings


def setup_auth(app: FastAPI) -> FastAPI:
    if settings.auth_type == "soauth":
        return global_setup(
            app=app,
            app_base_url=settings.soauth_base_url,
            authentication_base_url=settings.soauth_auth_url,
            app_id=settings.soauth_app_id,
            client_secret=settings.soauth_client_secret,
            public_key=settings.soauth_public_key,
            key_pair_type=settings.soauth_key_pair_type,
            add_middleware=True,
        )
    else:
        return mock_global_setup(app=app, grants=["simonsobs"])


def allow_proprietary(request: Request) -> bool:
    """
    Checks whether a request can have proprietary data returned
    from it or not.
    """

    return settings.proprietary_scope in request.auth.scopes


def filter_by_proprietary(query: Select, request: Request) -> Select:
    if not allow_proprietary(request=request):
        query = query.filter_by(proprietary=False)

    return query
