"""
Endpoints for highlights
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from .. import database as db
from .. import orm
from .auth import filter_by_proprietary

highlights_router = APIRouter(prefix="/highlights")


@highlights_router.get("/boxes")
def get_highlight_boxes(request: Request):
    with db.get_session() as session:
        stmt = filter_by_proprietary(select(orm.HighlightBox), request=request)
        results = session.exec(stmt).scalars().all()

    return results


@highlights_router.put("/boxes/new")
def add_highlight_box(
    top_left: tuple[float, float],
    bottom_right: tuple[float, float],
    description: str | None,
    name: str | None,
    request: Request,
):
    """
    Add a new highlight box. For conversion from selection regions.
    """
    with db.get_session() as session:
        new_box = orm.HighlightBox(
            top_left_ra=top_left[0],
            top_left_dec=top_left[1],
            bottom_right_ra=bottom_right[0],
            bottom_right_dec=bottom_right[1],
            description=description,
            name=name,
        )
        session.add(new_box)
        session.commit()
        new_id = new_box.id

    return new_id


@highlights_router.delete("/boxes/{id}")
def delete_highlight_box(id: int, request: Request):
    with db.get_session() as session:
        stmt = select(orm.HighlightBox).where(orm.HighlightBox.id == id)
        result = session.exec(stmt).scalars().one_or_none()

        if result is None:
            raise HTTPException(status_code=404, detail="Box not found")

        session.delete(result)
        session.commit()

    return
