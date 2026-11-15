FROM python:3.12.13-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 cafe \
    && useradd --uid 10001 --gid cafe --no-create-home --shell /usr/sbin/nologin cafe

FROM base AS code
COPY src/ /source/src/
RUN python -c "import shutil; shutil.copytree('/source/src', '/runtime/src', ignore=shutil.ignore_patterns('test', 'tests_js', '__pycache__', '*.sqlite3', '*.sqlite3-*'))"

FROM base AS runtime
COPY --from=code --chown=cafe:cafe /runtime/src/ ./src/
COPY --chown=cafe:cafe scripts/migrer_sqlite_vers_postgres.py scripts/donnees_v3.py ./scripts/
COPY --chown=cafe:cafe docker/gunicorn.conf.py docker/healthcheck.py docker/preparer_secrets.py ./docker/
RUN mkdir /app/staticfiles /app/secrets && chown cafe:cafe /app/staticfiles /app/secrets
USER cafe
EXPOSE 8000
CMD ["gunicorn", "--config", "docker/gunicorn.conf.py", "config.wsgi:application"]

FROM runtime AS tests
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=cafe:cafe src/CafeDolbeau/test/ ./src/CafeDolbeau/test/
COPY --chown=cafe:cafe src/CafeDolbeau/tests_js/ ./src/CafeDolbeau/tests_js/
COPY --chown=cafe:cafe scripts/_donnees_test.py scripts/donnees_v1.py scripts/donnees_v2.py ./scripts/
COPY --chown=cafe:cafe scripts/configurer_env.py ./scripts/
COPY --chown=cafe:cafe .env.example ./
COPY --chown=cafe:cafe docker/test.sh ./docker/
USER cafe
CMD ["sh", "docker/test.sh"]

# La construction sans --target produit également l’image de production.
FROM runtime AS production
