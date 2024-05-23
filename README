Tile Server
===========

A very simple tile server, backed by a SQL database, for astronomical maps.

The examples directories provide scripts to create 'example' databases out
of astronomical maps, and they can be served using the included FastAPI
server.

Settings are configured using a Pydantic settings model, and are defined
using configuration variables:

- `$TILEMAKER_DATABASE_URL`, the databse URL for SQLAlchemy.
   Defaults to `sqlite:///./test.db`,
- `$TILEMAKER_ORIGINS`, the list of potential origins for the
  data source. For example, `\[\"http://localhost\"\,\ \"http://localhost:1234\"\]`
  may be useful to export this to.
- `$TILEMAKER_ADD_CORS`, whether or not to add cross-origin support.
- `$TILEMAKER_STATIC_DIRECTORY`, the static directory to launch the SPA from.
  Used if you want to serve the frontend from the same FastAPI server.
- `$TILEMAKER_API_ENDPOINT`, the endpoint to serve the API from. defaults to
  `./`.

To set up a simple server, no configuration options are required. The defaults should
work.

Maps can be any valid FITS file. For instance, using the maps from the
ACT DR5 collection (https://lambda.gsfc.nasa.gov/product/act/actpol_dr5_coadd_maps_get.html),
one can generate a SQLite database in a fresh shell as follows:

```
python3 fits.py create act_dr5.01_s08s18_AA_f150_daynight_map.fits act_dr5.01_s08s18_AA_daynight_map
```

This will create `test.db` in your local directory filled with the tiles for the map, and may take
a minute or so. Note that the database will be a few gigabytes in size (typically there is an
overhead of around 25-50% over the base map itself, depending on compression).

You can serve the maps using `uvicorn`:

```
uvicorn tilemaker.server:app --port=9191 --reload
```

API docs are auto-generated and are available at `http://127.0.0.1:9191/docs`. You can view
map tiles at e.g. 

```
http://127.0.0.1:9191/maps/act_dr5.01_s08s18_AA_daynight_map/1/2/1/1/tile.webp?cmap=viridis&vmin=-100&vmax=100&log_norm=false&clip=true
```

See the API docs for more information.