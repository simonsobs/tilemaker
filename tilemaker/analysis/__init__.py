"""
Analysis and their caching mechanisms.
"""

from pydantic import BaseModel


class AnalysisProduct(BaseModel):
    name: str
    grant: str | None = None
