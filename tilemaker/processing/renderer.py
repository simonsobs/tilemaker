"""
Renderer for buffers to images.
"""

from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
from pydantic import BaseModel, Field


class RenderOptions(BaseModel):
    cmap: str = Field(default="viridis")
    "Color map to use for rendering, defaults to 'viridis', and may not be used if RGBA buffers are provided"
    vmin: float = Field(default=-100)
    "Color map range minimum, defaults to -100"
    vmax: float = Field(default=100)
    "Color map range maximum, defaults to 100"
    log_norm: bool = Field(default=False)
    "Whether to use a log normalization, defaults to False"
    abs: bool = Field(default=False)
    "Whether to take the absolute value of the data before rendering it"
    clip: bool = Field(default=False)
    "Whether to clip values outside of the range, defaults to True"
    flip: bool = Field(default=False)
    "Whether to render the entire field using 360 -> RA convention (true) or -180 < RA < 180 (false)"

    @property
    def norm(self) -> plt.Normalize:
        if self.log_norm:
            return LogNorm(vmin=self.vmin, vmax=self.vmax, clip=self.clip)
        else:
            return plt.Normalize(vmin=self.vmin, vmax=self.vmax, clip=self.clip)


class Renderer:
    format: Optional[str]
    "Format to render images to, defaults to 'webp'."
    pil_kwargs: Optional[dict[str, Any]]
    "Keyword arguments to pass to PIL for rendering, defaults to None."

    def __init__(
        self,
        format: Optional[str] = "webp",
        pil_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.format = format
        self.pil_kwargs = pil_kwargs

        return

    def render(
        self,
        fname: Union[str, Path, BinaryIO],
        buffer: np.ndarray,
        render_options: RenderOptions,
    ):
        """
        Renders the buffer to the given file.

        Parameters
        ----------
        fname : Union[str, Path, BinaryIO]
            Output for the rendering.
        buffer : np.ndarray
            Buffer to render to disk or IO.
        render_options : RenderOptions
            Options for rendering.

        Notes
        -----

        Buffer is transposed in x, y to render correctly within this function.
        """

        if render_options.flip:
            # Flip the buffer horizontally if requested.
            buffer = np.fliplr(buffer)

        if render_options.abs:
            buffer = np.abs(buffer)

        if buffer.ndim == 2:
            # Render with colour mapping, this is 'raw data'.
            cmap = plt.get_cmap(render_options.cmap)
            cmap.set_bad("#dddddd", 0.0)
            mapped = cmap(render_options.norm(buffer))
            plt.imsave(
                fname,
                mapped,
                pil_kwargs=self.pil_kwargs,
                format=self.format,
                origin="lower",
            )
        else:
            # Direct rendering
            plt.imsave(
                fname,
                np.ascontiguousarray(buffer.swapaxes(0, 1)),
                pil_kwargs=self.pil_kwargs,
                format=self.format,
            )

        return
