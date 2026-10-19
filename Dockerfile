# MultiRegistrator server image.
#
# The server polls Modbus/TCP devices, serves the HTTP API and mirrors the
# archive + logs into PostgreSQL.  Built from the sources in this repository;
# run it together with the database and pgAdmin via docker-compose.yml.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    QT_QPA_PLATFORM=offscreen \
    MULTIREGISTRATOR_DB_ENABLED=1 \
    MULTIREGISTRATOR_DB_HOST=postgres \
    MULTIREGISTRATOR_DB_PORT=5432 \
    MULTIREGISTRATOR_DB_NAME=multiregistrator \
    MULTIREGISTRATOR_DB_USER=multiregistrator

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY multiregistrator ./multiregistrator
COPY packaging ./packaging
COPY config ./config
COPY pyproject.toml ./

RUN mkdir -p /app/archive /app/logs

EXPOSE 8120

# Headless mode: no GUI is needed inside the container.
CMD ["python", "-m", "multiregistrator.server.app", "--headless"]
