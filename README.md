TileMaker
=========

A very simple tile server, backed by a SQL database, for astronomical maps.

The package includes command-line tools to create databases out
of astronomical maps, and they can be served using the included FastAPI
server.

Settings are configured using a Pydantic settings model, and are defined
using configuration variables:

- `$TILEMAKER_DATABASE_URL`, the databse URL for SQLAlchemy.
   Defaults to `sqlite:///./tilemaker.db`,
- `$TILEMAKER_ORIGINS`, the list of potential origins for the
  data source. For example, `\[\"http://localhost\"\,\ \"http://localhost:1234\"\]`
  may be useful to export this to.
- `$TILEMAKER_ADD_CORS`, whether or not to add cross-origin support.
- `$TILEMAKER_API_ENDPOINT`, the endpoint to serve the API from. defaults to
  `./`.
- `$TILEMAKER_SERVE_FRONTEND`, a boolean telling you whether or not to serve
  the frontend. If you are using a pre-packaged setup, you should leave this alone.

To set up a simple server, no configuration options are required. The defaults should
work. You can install a pre-packaged version from the python packaging index:

```
uv pip install tilemaker
```

Ingesting Maps
--------------

Maps can be any valid FITS file. For instance, using the maps from the
ACT DR5 collection (https://lambda.gsfc.nasa.gov/product/act/actpol_dr5_coadd_maps_get.html),
one can generate a SQLite database in a fresh shell as follows:

```
tilemaker-fits-ingest act_dr5.01_s08s18_AA_f150_daynight_map.fits act_dr5.01_s08s18_AA_daynight_map
```

This will create `tilemaker.db` in your local directory filled with the tiles for the map, and may take
a minute or so. Note that the database will be a few gigabytes in size (typically there is an
overhead of around 25-50% over the base map itself, depending on compression). It will create a
new layer for each band in the file. If you just want to have the intensity, use `--intensity-only`.

To remove maps you can use `tilemaker-remove`, or you can just delete the sqlite database and
start again.


Viewing Maps
------------

The pypi and docker images come pre-built with the frontend. You can run the server with

```
tilemaker-serve --host localhost --port 8000
```

where the two parameters are optional.
