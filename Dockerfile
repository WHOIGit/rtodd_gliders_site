FROM python:3.12-slim

ARG PANDOC_VERSION=2.9.2.1

# Prevents Python from writing pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional but common). Keep minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Match the Pandoc version currently used on the server for BibTeX conversion.
RUN curl -fsSLo /tmp/pandoc.deb \
       "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/pandoc.deb \
    && rm -f /tmp/pandoc.deb \
    && rm -rf /var/lib/apt/lists/*

# Copy application code and install the project from pyproject.toml
COPY pyproject.toml README.md /app/
COPY src/ /app/src/
COPY bibtex/ /app/bibtex/
RUN pip install --no-cache-dir .

# --no-control-socket: the container runs as a UID with no home directory
# (see `user:` in compose.yml), so gunicorn's control socket would try to
# create /.gunicorn/ and fail with EACCES. We don't use `gunicornc` runtime
# management, so disable the socket entirely.
CMD ["gunicorn", "--no-control-socket", "-b", "0.0.0.0:8050", "gliderapp.app:server"]
