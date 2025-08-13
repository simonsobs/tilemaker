from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, TypeAdapter


class Source(BaseModel):
    name: str | None = None
    ra: float
    dec: float
    extra: dict[str, Any] | None


class SourceProvider(BaseModel):
    file_type: Literal["csv", "json"]
    filename: Path

    def realize_sources(self) -> list[Source]:
        if self.file_type == "json":
            with open(self.filename, "r") as f:
                return TypeAdapter(list[Source]).validate_json(f.read())
        elif self.file_type == "csv":
            # Extra not supported
            data = np.loadtxt(self.filename, delimiter=",", skiprows=1)

            return [Source(name=x[0], ra=x[1], dec=x[2], extra=None) for x in data]


class SourceGroupStub(BaseModel):
    source_group_id: str
    name: str
    description: str | None = None


class SourceGroup(SourceGroupStub):
    sources: list[Source] | None = None
    grant: str | None = None
    provider: SourceProvider | None = None

    def model_post_init(self, _):
        if self.provider is not None:
            self.sources = self.provider.realize_sources()
