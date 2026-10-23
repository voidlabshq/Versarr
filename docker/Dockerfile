FROM python:3.12-slim-bookworm AS builder

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

RUN pip install --upgrade pip && pip install .

FROM python:3.12-slim-bookworm AS runtime

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

RUN groupadd --gid 1000 versarr \
    && useradd --create-home --uid 1000 --gid 1000 versarr \
    && mkdir -p /state /app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/alembic.ini /app/alembic.ini
COPY --from=builder /build/alembic /app/alembic

RUN chown -R versarr:versarr /state /app /opt/venv

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER versarr
EXPOSE 9280
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import json, os, sys, urllib.request as u; port = os.environ.get('VERSARR_HTTP_BIND_PORT', '9280'); sys.exit(0 if json.load(u.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)).get('status') == 'ok' else 1)"]
ENTRYPOINT ["/entrypoint.sh"]
CMD ["versarr", "serve"]

