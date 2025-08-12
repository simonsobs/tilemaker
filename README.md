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
`TILEMAKER_PRECACHE="yes"`, which will give you a longer startup time but
will avoid any potential slowdown when paging through maps in the viewer.

The server will print some things to the terminal as it performs its internal
startup process. It is ready when you recieve the lines:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

To view your maps, all you need to do is to go to
[http://localhost:8000](http://localhost:8000) in a web browser.


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

#### Configuring Memcached

#### Configuring SOAuth

#### Guinicorn Specification


### Tile Specification

### Source Specification

### Highlight Boxes

