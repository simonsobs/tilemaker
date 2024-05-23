FROM python:3.11

# Note you will need to build the frontend and copy it here... For now.
COPY dist static
COPY templates templates
COPY . livetiler

RUN pip install --no-cache-dir --upgrade ./livetiler
RUN pip install --no-cache-dir --upgrade "gunicorn"
RUN pip install --no-cache-dir --upgrade "psycopg[binary,pool]"

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "8", "tilemaker.server:app", "--bind", "0.0.0.0:8080"]