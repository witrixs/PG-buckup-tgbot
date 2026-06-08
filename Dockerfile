FROM python:3.12-slim-bookworm

ARG PG_CLIENT_VERSIONS="16 17"
ENV TZ=Europe/Moscow

WORKDIR /app

# pg_dump/pg_restore внутри контейнера
# Base image = bookworm, PGDG repo = bookworm-pgdg (должны совпадать!)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg tzdata && \
    ln -sf /usr/share/zoneinfo/Europe/Moscow /etc/localtime && \
    echo "Europe/Moscow" > /etc/timezone && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    for version in ${PG_CLIENT_VERSIONS}; do \
      apt-get install -y --no-install-recommends postgresql-client-${version}; \
    done && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/
COPY main.py .

RUN mkdir -p /backups /var/log

CMD ["python", "main.py"]
