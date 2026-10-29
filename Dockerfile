# ------------------------------------------------------------
# Frontend build stage
# ------------------------------------------------------------
FROM node:26-bookworm-slim AS frontend-builder

WORKDIR /

# git is only needed to fetch tileviewer
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Clone and build tileviewer
RUN git clone https://github.com/simonsobs/tileviewer.git

WORKDIR /tileviewer

# Clean any potentially stale Vite artifacts, then install and build
RUN npm cache clean --force \
    && rm -rf node_modules/.vite \
    && npm install \
    && npm run build


# ------------------------------------------------------------
# Python runtime stage
# ------------------------------------------------------------
FROM python:3.13-bookworm

WORKDIR /livetiler

# Copy this repo's Python code
COPY ./tilemaker ./tilemaker
COPY ./pyproject.toml ./pyproject.toml

# Copy the compiled frontend from the Node build stage
RUN rm -rf tilemaker/server/static \
    && mkdir -p tilemaker/server/static

COPY --from=frontend-builder \
    /tileviewer/dist/ \
    ./tilemaker/server/static/

# Install Python application and runtime server
RUN pip install --no-cache-dir --upgrade . \
    && pip install --no-cache-dir --upgrade gunicorn

EXPOSE 8000

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "8", "tilemaker.server:app", "--bind", "0.0.0.0:8000"]
