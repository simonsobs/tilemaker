"""
Sources router
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from .. import database as db
from .. import orm
from .auth import filter_by_proprietary

sources_router = APIRouter(prefix="/sources")


@sources_router.get("")
def get_sources(request: Request):
    with db.get_session() as session:
        stmt = filter_by_proprietary(select(orm.SourceList), request=request)
        results = session.exec(stmt).scalars().all()

    return results


@sources_router.get("/{id}")
def get_source_list(id: int, request: Request):
    with db.get_session() as session:
        stmt = filter_by_proprietary(
            select(orm.SourceItem).where(orm.SourceItem.source_list_id == id),
            request=request,
        )
        result = session.exec(stmt).scalars().all()

    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")

    return result
