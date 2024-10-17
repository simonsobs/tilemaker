FROM python:3.11

WORKDIR /

# Clone client and build it; also clean cache to ensure no strange vite build issues
RUN apt-get update && apt-get install -y git nodejs npm
RUN git clone https://github.com/simonsobs/tileviewer.git
WORKDIR /tileviewer
RUN echo "VITE_SERVICE_URL=https://nersc.simonsobs.org/beta/maps \nVITE_BASE_PATH=beta/newmaps/static/" > .env.production
RUN npm cache clean --force
RUN rm -rf node_modules/.vite
RUN npm install
RUN npm run build

# Copy this repo's code into a directory called livetiler
WORKDIR /
COPY . livetiler

# Copy client's build into livetiler's static directory, ensuring a clean copy,
# then delete client repo
WORKDIR /livetiler
RUN rm -rf static && mkdir -p static
RUN cp -r /tileviewer/dist/* static/
RUN rm -rf /tileviewer

RUN pip install --no-cache-dir --upgrade .
RUN pip install --no-cache-dir --upgrade "gunicorn"
RUN pip install --no-cache-dir --upgrade "psycopg[binary,pool]"

EXPOSE 8080

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "8", "tilemaker.server:app", "--bind", "0.0.0.0:8080"]