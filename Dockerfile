FROM python:3.11

# Note you will need to build the frontend and copy it here... For now.
COPY dist static
COPY templates templates
COPY . livetiler
RUN pip install --no-cache-dir --upgrade "matplotlib"
RUN pip install --no-cache-dir --upgrade ./livetiler
RUN pip install --no-cache-dir --upgrade "psycopg[binary,pool]"

CMD ["uvicorn", "--port", "8080", "--host", "0.0.0.0", "tilemaker.server:app"]