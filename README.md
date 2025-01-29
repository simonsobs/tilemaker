TileMaker
=========

A very simple tile server, backed by a SQL database, for astronomical maps.

The package includes command-line tools to create databases out
of astronomical maps, and they can be served using the included FastAPI
server.

Installation and Usage
----------------------

It is recommended that you install tilemaker in a virtual environment. You can
easily manage virtual environments using python's built in `venv` tool or
using `uv`. We recommend `uv`.

```
uv venv venv --python=3.12
source venv/bin/activate
uv pip install tilemaker
```

OR if you don't ever want to install anything, just:

```
uv run --python=3.12 --with tilemaker tilemaker $OPTIONS
```

All user-driven usage of `tilemaker` is performed using the `tilemaker`
command line utility. More information is available using `tilemaker --help`.

Ingesting Data
--------------

Currently, we support TWO major types of data ingest.

### IQU Maps

IQU maps in the CAR representation can be ingested using 

```
tilemaker add iqu $FILENAME $NAME
```

There are lots more options that can be seen with `tilemaker add iqu --help`. For example:

```
tilemaker add iqu my_file.fits "An Example Map" --intensity-only
```

To ingest only the `I` component of the map. Note that the default units are in `uK`, so if your
map has un-declared (in the FITS header) kelvin units, you will need to add `--units=K`.

### Catalog Ingest

Catalogs in two major formats can be ingested. CSV and JSON, using

```
tilemaker add catalog $FILENAME $NAME $DESCRIPTION
```

for example

```
tilemaker add catalog example.json "Example Catalog" "Description of my example catalog"
```

#### CSV Layout

CSV files must be in the following format and have extension `.csv`:

```
# FLUX, RA, DEC
0.9222,36.03,-18.32
0.2222,34.22,19.22
0.9522,26.03,-18.32
0.2522,24.22,19.22
```

#### JSON Layout

JSON files must be in the following format and have extension `.json`:

```
[
  {
    "ra": 90.222,
    "dec": -12.34,
    "flux": 12.3,
    "name": "Favourite"
  },
  {
    "ra": 22.222,
    "dec": -19.34,
    "flux": 11.3
  }
]
```


Viewing Maps
------------

The pypi and docker images come pre-built with the frontend. You can run the server with

```
tilemaker serve --port=8080
```

where the port parameter is optional.


Settings
--------

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

To set up a simple server, no configuration options are required. 

