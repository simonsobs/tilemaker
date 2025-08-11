from typing import Any

from pydantic import BaseModel


class Source(BaseModel):
    extra: dict[str, Any]


class SourceGroup(BaseModel):
    ra: float
    dec: float
    sources: list[Source]
