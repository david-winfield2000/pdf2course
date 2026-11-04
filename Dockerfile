FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends build-essential swig curl \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv

# The book's exact libraries, plus what this app needs to serve them
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /opt/book
COPY hidden/handson-mlp/pyproject.toml hidden/handson-mlp/uv.lock ./
RUN uv sync --frozen --no-install-project \
    && uv pip install --python /opt/venv/bin/python box2d-py fastapi "uvicorn[standard]" pymupdf

WORKDIR /app
COPY server.py fetch_resources.py pdf2lesson.py ./
COPY static ./static

EXPOSE 8000
CMD ["sh", "-c", "python fetch_resources.py & exec uvicorn server:app --host 0.0.0.0 --port 8000"]
