# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.14-slim@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-default-groups --no-editable

FROM python:3.14-slim@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
# rasterio's wheel bundles GDAL but links the system's expat. pip is not needed at run time,
# and its vendored copies of urllib3, msgpack and setuptools lag behind their fixes.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall --yes --quiet --root-user-action ignore pip
RUN useradd --system --uid 10001 --no-create-home --home-dir /nonexistent jugrid \
 && mkdir -p /cache && chown 10001 /cache
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 JUGRID_CACHE_DIR=/tmp/jugrid HOME=/tmp
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]
CMD ["uvicorn", "jugrid.api.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
