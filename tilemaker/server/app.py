"""
Main server app.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..settings import settings
from .auth import setup_auth
from .highlights import highlights_router
from .histogram import histogram_router
from .maps import maps_router
from .sources import sources_router


async def lifespan(app: FastAPI):
    """
    Lifespan event handler for the FastAPI app.
    """

    settings.setup_app(app=app)

    yield


tags_metadata = [
    {
        "name": "Maps and Tiles",
        "description": "Operations to retrieve metadata about maps, bands, and layers, as well as the tiles themselves.",
    },
    {
        "name": "Histograms",
        "description": "Operations for getting details about histograms and color maps.",
    },
    {
        "name": "Sources",
        "description": "Operations for getting point source information.",
    },
    {"name": "Highlights", "description": "Operations for gettting highlight boxes."},
]

app = FastAPI(lifespan=lifespan, openapi_tags=tags_metadata)
STATIC_DIRECTORY = Path(__file__).parent / "static"

if settings.add_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app = setup_auth(app)

app.include_router(highlights_router)
app.include_router(histogram_router)
app.include_router(sources_router)
app.include_router(maps_router)

if settings.serve_frontend:
    # The index.html is actually in static. But if anyone wants to access it
    # they might go to /, /index.html, /index.htm... etc. So we need to have a
    # catch-all route for static content
    @app.get("/")
    async def serve_spa():
        index_file_path = STATIC_DIRECTORY / "index.html"
        return FileResponse(index_file_path)


# Mount the built-in client.
if settings.serve_frontend:
    app.mount("/", StaticFiles(directory=STATIC_DIRECTORY), name="spa")
