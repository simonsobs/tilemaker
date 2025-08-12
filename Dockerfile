FROM python:3.11

WORKDIR /

# Clone client and build it; also clean cache to ensure no strange vite build issues
RUN apt-get update && apt-get install -y git nodejs npm
RUN git clone https://github.com/simonsobs/tileviewer.git
WORKDIR /tileviewer
RUN npm cache clean --force
RUN rm -rf node_modules/.vite
RUN npm install
RUN npm run build

# Copy this repo's code into a directory called livetiler
WORKDIR /
COPY ./tilemaker livetiler/tilemaker
COPY ./pyproject.toml livetiler/pyproject.toml

# Copy client's build into livetiler's static directory, ensuring a clean copy,
# then delete client repo
WORKDIR /livetiler
RUN rm -rf tilemaker/server/static && mkdir -p tilemaker/server/static
RUN cp -r /tileviewer/dist/* tilemaker/server/static 
RUN rm -rf /tileviewer

RUN pip install --no-cache-dir --upgrade .
RUN pip install --no-cache-dir --upgrade "gunicorn"

EXPOSE 8000

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "8", "tilemaker.server:app", "--bind", "0.0.0.0:8000"]
