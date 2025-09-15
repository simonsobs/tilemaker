TileMaker
=========

TileMaker, along with its frontend, TileViewer, is a tool for visualizing
and analyzing astronomical maps with an equirectangular projection, like those
used by the Atacama Cosmology Telescope and Simons Observatory.

TileMaker uses the HTTP protocol to serve your tiles over a network connection,
meaning that the server running the analysis can be in a completely different
place than where you're viewing them. This helps when you have maps stored
on a remote machine (e.g. a HPC facility) but want to view them on your
laptop, no large file transfer necessary!

TileMaker can be used in a number of modes:

+ Locally to visualize and organize a colleciton of maps.
+ Remotely over an SSH connection to view maps on an external machine.
+ In 'production' mode, served from a docker container (see e.g. 
  [the Simons Observatory main viewer](https://maps.simonsobservatory.org))

TileMaker excels over its competition by not requiring any pre-ingestion
process and by not creating any ancillary files. To reduce load on
filesystems, we support local in-memory caches (primarily for use in
the 'investigative' local and remote modes) as well as `memcached`
for production modes where multithreaded ASGI servers are recommended.

Installation and Usage
----------------------

It is recommended that you install tilemaker in a virtual environment. You can
easily manage virtual environments using python's built in `venv` tool or
using `uv`. We recommend `uv`.

```
uv venv --python=3.12
source .venv/bin/activate
uv pip install tilemaker
```

OR if you don't ever want to install anything, just:

```
uv run --python=3.12 --with tilemaker tilemaker $OPTIONS
```

Simple Usage
------------

To start using tilemaker with your equirectangular maps, you can simply run:

```
tilemaker open *.fits
```

This will open all of the fits files in your current working directory. If you
want to improve first-run performance, you can set the environment variable
`TILEMAKER_PRECACHE=yes` (the default, to turn off set `no`), which will give
you a longer startup time but will avoid any potential slowdown when paging
through maps in the viewer.

The server will print some things to the terminal as it performs its internal
startup process. It is ready when you recieve the lines:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

To view your maps, all you need to do is to go to
[http://localhost:8000](http://localhost:8000) in a web browser.

You can also use

```
tilemaker dev
```

which will launch an example version of the viewer containing sample data.


Remote Usage
------------

Remote usage is very similar to the 'Simple Usage' case outlined above, but you
will need to consider two things. First, if you are using a shared machine, the
port 8000 may already be in use by others. By using
`tilemaker open *.fits --port=$SOME_NUMBER`, you can choose the port that is used.

Second, if you are connected to the machine over SSH, you should use port
forwarding. That can be accomplished through the `-L` option on most SSH
clients.

For example, let's say I run my server on port 9182:

```
ssh -L localhost:9182:localhost:9182 my.domain.com
...
tilemaker open *.fits --port=9182
```

Then, you can go to [http://localhost:9182](http://localhost:9182) on the
machine you are using to connect to the remote and render the viewer there.
It's important to ensure that your map has the correct `BUNIT` value in the
header. We attempt to 'guess' what the units should be for various maps,
but telling the difference between e.g. `uK` and `K` maps is nontrivial.

A good example map to start with is one of the
[ACT DR6.02 Coadd maps](https://lambda.gsfc.nasa.gov/product/act/act_dr6.02/act_dr6.02_maps_coadd_get.html).

Production Usage
----------------

When running TileMaker in 'production', which we very loosely define as a
server running at a fixed place on the open internet, we strongly recommend
using a docker container. We provide such a container on DockerHub
at [simonsobs/tilemaker](https://hub.docker.com/r/simonsobs/tilemaker).

There are a number of other considerations here.

1. You will need to use the configuration file (described below) rather
   than the 'open all the fits files' method described above.
2. It's recommended that you run the server using more than one thread.
   By default the docker container runs with eight threads.
3. You may wish to use `memcached` as a caching service rather than
   the default thread-local cache. This allows all of your threads to
   share the same tile and analysis cache.
4. If you want to protect some of your maps away from prying eyes, you can
   use [SOAuth](https://github.com/simonsobs/soauth), which is the
   Simons Observatory shared authentication framework. This provides each user
   with a number of 'grants' that define their ability to view various pieces
   of data, and is backed by a GitHub login.
5. We generally recommend running tilemaker behind an `nginx` or other reverse
   proxy that supports HTTP/2. This is generally already the case if you are
   using a hosted kubernetes service with e.g. ingress support. HTTP/2 allows
   browsers to make many parallel requests for tiles from the server, whereas
   by default (HTTP/1.1) you can only make six at a time!

Configuring TileMaker
---------------------

### Environment Variables

There are a number of environment variables that are used to configure the
TileMaker server. We set these to reasonable defaults, but you might want
to change them (and should if you are running in production mode)! They
all should be prepended by `TILEMAKER_`.

- `CONFIG_PATH`: the path to your data configuration file. By default this is
  `sample.json`
- `ORIGINS` and `ADD_CORS`: whether to allow CORS. By default we do, and you
   will need to if you are behind a reverse proxy.
- `SERVE_FRONTEND`: Whether to serve the frontend from `/`, otherwise we just
   serve the API. By default this is `yes`.
- `API_ENDPOINT`: The root endpoint the API is served from, by default `/`.
- `AUTH_TYPE`: Either `mock` (no authentication), or `soauth` if you are using
  SOAuth integration (see below for additional details).
- `CACHE_TYPE`: one of `in_memory` (default) or `memcached` (see below for
  the details of configuring memcached).
- `PRECACHE`: whether or not to precache the histograms and top-level tiles.
  By default `yes`.


#### Configuring Memcached

Memcached should be set up as a server on the same local network as your
TileMaker instance. You should not use a remote memcached service for tilemaker
as the latency will be too high.

You will need to increase the maximum individual item cache size depending
on your tile size. Note that we usually store tiles as 32 bit floats, so
e.g. if you have a 675 x 675 tile size (common with ACT and SO maps), each
tile represents ~2 MB of data. To be safe, we recommend increasing the cache
size to 16 MB: `-l 16m`.

The size of the cache should be approximately the same size as your on-disk
maps if at all possible. For production instances, we typically use a 32 or 64
GB cache size when serving a few hundred maps and this works well (`-m 32768`).
So your full memcached command should be:

```
memcached -m 32768 -l 16m
```

You can configure memcached using the following environment variables (remember
to prefx with `TILEMAKER_`):

- `MEMCACHED_HOST`: the hostname of the memcached service (default `localhost`)
- `MEMCACHED_PORT`: 11211.
- `MEMCACHED_CLIENT_POOL_SIZE`: the number of clients in the memcached pool.
  Defaults to 4. Note that these clients are threadlocal.
- `MEMCACHED_TIMEOUT_SECONDS`: 0.5, the default timeout for memcached operations.
  Because of the relatively large cache size, this needs to be increased from the
  very small default in `pymemcache`.

We run in production with the default settings, aside from changing the host
specification.

#### Configuring SOAuth

[SOAuth](https://github.com/simonsobs/soauth) is the shared identity and
authentication framework for Simons Observatory services. It is a decentralized
system, with the main identity server providing encrypted tokens that are
then decrypted by the services themselves (like TileMaker). As such,
you will need to configure (prefixed with `TILEMAKER_`):

- `SOAUTH_BASE_URL`: The base URL of your application.
- `SOAUTH_AUTH_URL`: The URL of your authentication service (i.e. where SOAuth
   runs)
- `SOAUTH_APP_ID`: The APP ID of your SOAuth app.
- `SOAUTH_CLIENT_SECRET`: The client secret from SOAuth.
- `SOAUTH_PUBLIC_KEY`: The public key from SOAuth.
- `SOAUTH_KEY_PAIR_TYPE`: The key pair type provided by SOAuth.

These are all standard configuration variables for SOAuth, and there is
significantly more description available on them from the SOAuth documentation.

#### Guinicorn Specification

The docker container that we provide runs `gunicorn` with 8 worker threads by
default with the following configuration:

```
gunicorn -k uvicorn.workers.UvicornWorker \
         -w 8 \
         tilemaker.server:app \
         --bind 0.0.0.0:8000
```

You can modify this with your launch command to modify the number of workers.

Data Configuration
------------------

If you want to have more fine control over your data, and potentially include
sources and highlight regions, you will need to create a configuration file.
This configuration file is a JSON file, and has three main sections outlined
below.

### Tile Specification

Tiles are specified as part of 'Map Groups'. There is a specific hierarchy
here that allows you to assign multiple maps together. This hierarchy
is as follows:

- Map Group (a collection of maps, e.g. the ACT DR6.02 Release)
- Map (a 'type' of map, e.g. a specific map type in ACT DR6.02 like ACTxPlanck DayNight)
- Band (e.g. frequency band, e.g. f090)
- Layer (an individual 2D FITS array, e.g. I, Q, or U).

An example map group:

```json
{
  "map_groups": [
    {
      "name": "ACT DR6.02",
      "description": "Maps from DR6.02 from the Atacama Cosmology Telescope",
      "maps": [
        {
          "map_id": "1",
          "name": "ACT DR4-DR6 x Planck",
          "description": "All ACT data cross-correlated with Planck.",
          "bands": [
            {
              "band_id": "1",
              "name": "f090",
              "description": "Frequency band f090",
              "layers": [
                {
                  "layer_id": "f090I",
                  "name": "I",
                  "description": "Intensity map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f090_map.fits",
                    "index": 0
                  },
                  "quantity": "T (I)",
                  "units": "uK",
                  "vmin": -500,
                  "vmax": 500,
                  "cmap": "RdBu_r"
                },
                {
                  "layer_id": "f090Q",
                  "name": "Q",
                  "description": "Q-polarization map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f090_map.fits",
                    "index": 1
                  },
                  "quantity": "T (Q)",
                  "units": "uK",
                  "vmin": -50,
                  "vmax": 50,
                  "cmap": "RdBu_r"
                },
                {
                  "layer_id": "f090U",
                  "name": "U",
                  "description": "U-polarization map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f090_map.fits",
                    "index": 2
                  },
                  "quantity": "T (U)",
                  "units": "uK",
                  "vmin": -50,
                  "vmax": 50,
                  "cmap": "RdBu_r"
                }
              ]
            },
            {
              "band_id": "2",
              "name": "f150",
              "description": "Frequency band f150",
              "layers": [
                {
                  "layer_id": "f150I",
                  "name": "I",
                  "description": "Intensity map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f150_map.fits",
                    "index": 0
                  },
                  "quantity": "T (I)",
                  "units": "uK",
                  "vmin": -500,
                  "vmax": 500,
                  "cmap": "RdBu_r"
                },
                {
                  "layer_id": "f150Q",
                  "name": "Q",
                  "description": "Q-polarization map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f150_map.fits",
                    "index": 1
                  },
                  "quantity": "T (Q)",
                  "units": "uK",
                  "vmin": -50,
                  "vmax": 50,
                  "cmap": "RdBu_r"
                },
                {
                  "layer_id": "f150U",
                  "name": "U",
                  "description": "U-polarization map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f150_map.fits",
                    "index": 2
                  },
                  "quantity": "T (U)",
                  "units": "uK",
                  "vmin": -50,
                  "vmax": 50,
                  "cmap": "RdBu_r"
                },
                {
                  "layer_id": "f150Iivar",
                  "name": "I (ivar)",
                  "description": "Intensity inverse-variance map",
                  "provider": {
                    "provider_type": "fits",
                    "filename": "act-planck_dr4dr6_coadd_AA_daynight_f150_ivar.fits",
                    "index": 0
                  },
                  "quantity": "IVar",
                  "grant": "ivaraccess",
                  "units": "uK^-2",
                  "vmin": 100000,
                  "vmax": 10000000000,
                  "cmap": "viridis"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Here we use three files that contain I, Q, U maps and specify their color map ranges
and color maps. We also assign another band from the inverse variance map for the
`f150` frequency band.

You can restrict access at any level with the optional `grant` keyword. Users
without this specific grant will not be able to access it (e.g.
`"grant":"ivaraccess"` in the above).

#### Getting a Starting Point

You can generate the configuration that would be created for the `tilemaker open`
command with:
```
tilemaker genconfig *.fits --output my_output_file.json
```

### Source Specification

Sources are specified as part of 'Source Groups' which are effectively individual
catalogs, and are provided by catalogs in a JSON format.

```json
"source_groups": [
    {
      "name": "Example",
      "description": "An example catalogue",
      "provider": {
        "file_type": "json",
        "filename": "example/example_cat.json"
      }
    }
  ]
```

#### Source Catalog Format

For each source, you should provide the RA, Dec, and name. You can add an additional dictionary
called 'extra' that will be rendered in the UI. For example:

```json
[
  {
    "ra": 90.222,
    "dec": -12.34,
    "name": "Favourite",
    "extra": {
      "flux": 9.23,
      "snr": 1.2
    }
  },
  {
    "ra": 22.222,
    "dec": -19.34,
    "name": "The worst",
    "extra": {
      "flux": 9.23,
      "snr": 1.2
    }
  }
]
```

### Highlight Boxes

Highlight boxes are areas of the UI that are downloadable. Users can define their own highlight
boxes using tools in the interface, but sometimes it's helpful to have pre-defined ones that
e.g. show a specific survey patch.

```json
"boxes": [
   {
   "name": "BOSS-N",
   "description": "Example box, for the BOSS-N region.",
   "top_left_ra": -200.0,
   "top_left_dec": 20.0,
   "bottom_right_ra": -120.0,
   "bottom_right_dec": 0.0
   }
]
```

Map Viewer
----------

### Overview

### The Histogram

### Layer Switching

### Searching and Moving

### Sources

### Boxes


Underlying API
--------------

The TileMaker service hosts a readonly HTTP API that is used to power the frontend.
You can view the documentation for that API through the auto-generated API
docs avaialable at `/docs`.
