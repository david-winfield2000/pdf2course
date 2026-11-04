#!/bin/sh
# Build and run everything in Docker, at http://127.0.0.1:8000. Ctrl+C stops it.
set -e
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
    echo "Starting Docker..."
    open -a Docker
    until docker info >/dev/null 2>&1; do sleep 2; done
fi

mkdir -p "$HOME/scikit_learn_data" "$HOME/.cache/huggingface"
docker build -t pdf2course .
docker rm -f pdf2course >/dev/null 2>&1 || true  # replace any previous run
docker run --rm -it --name pdf2course \
    -p 127.0.0.1:8000:8000 \
    -v "$PWD/hidden:/app/hidden" \
    -v "$HOME/scikit_learn_data:/root/scikit_learn_data" \
    -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
    pdf2course
