#!/bin/sh
# Build and run everything in Docker in the background. ./stop.sh stops it.
set -e
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
    echo "Starting Docker..."
    open -a Docker
    until docker info >/dev/null 2>&1; do sleep 2; done
fi

mkdir -p progress "$HOME/scikit_learn_data" "$HOME/.cache/huggingface"
docker build -t pdf2course .
docker rm -f pdf2course >/dev/null 2>&1 || true  # replace any previous run
docker run --rm -d --name pdf2course \
    -p 127.0.0.1:8000:8000 \
    -v "$PWD/hidden:/app/hidden" \
    -v "$PWD/progress:/app/progress" \
    -v "$HOME/scikit_learn_data:/root/scikit_learn_data" \
    -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
    pdf2course >/dev/null
echo "Running at http://127.0.0.1:8000 (logs: docker logs -f pdf2course, stop: ./stop.sh)"
