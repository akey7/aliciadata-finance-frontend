# Container image for the production deployment, built by Dokploy on the VPS
# (see docs/ARCHITECTURE_AND_INSTALLATION.md). Dependencies come from uv.lock.

# Python pinned to the same patch version as .python-version.
FROM python:3.13.5-slim-bookworm

# uv pinned to the version the pre-commit hooks use.
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

# Use the image's Python (never download another one), and keep the virtual
# environment at a fixed path.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first, so code-only changes reuse this layer. --locked fails
# the build if uv.lock does not match pyproject.toml.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY app.py data_loading.py s3_downloader.py ./

# Run as a non-root user that can write only the download cache.
RUN useradd --create-home appuser && mkdir input && chown appuser input
USER appuser

# Configuration and secrets come from the environment (e.g. Dokploy's
# environment settings), never from a .env file in the image. Gradio listens
# on all interfaces so the container's port can be published.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
