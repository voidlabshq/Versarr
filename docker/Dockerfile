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

RUN useradd --create-home --uid 10001 versarr \
    && mkdir -p /state /app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/alembic.ini /app/alembic.ini
COPY --from=builder /build/alembic /app/alembic

RUN chown -R versarr:versarr /state /app /opt/venv

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER versarr
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["versarr", "serve"]

