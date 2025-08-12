from pydantic import BaseModel


class Box(BaseModel):
    name: str
    description: str | None = None
    top_left_ra: float
    top_left_dec: float
    bottom_right_ra: float
    bottom_right_dec: float
    grant: str | None = None
