#!/bin/sh
# Build and run everything in Docker in the background. ./stop.sh stops it.
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
docker run --rm -d --name pdf2course \
    -p 127.0.0.1:8000:8000 \
    -v "$PWD/hidden:/app/hidden" \
    -v pdf2course-progress:/app/progress \
    -v "$PWD/static:/app/static" \
    -v "$HOME/scikit_learn_data:/root/scikit_learn_data" \
    -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
    pdf2course >/dev/null
# Rebuild static/app.js whenever frontend/main.js changes (static/ is mounted, so just refresh the page)
if [ -f .watch.pid ]; then kill "$(cat .watch.pid)" 2>/dev/null || true; fi
(cd frontend && nohup node_modules/.bin/esbuild main.js --bundle --minify --format=esm --outfile=../static/app.js --watch=forever >../.watch.log 2>&1 & echo $! >../.watch.pid)
echo "Running at http://127.0.0.1:8000 (logs: docker logs -f pdf2course, stop: ./stop.sh)"
