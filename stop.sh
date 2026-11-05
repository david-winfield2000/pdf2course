#!/bin/sh
# Stop the server started by start.sh.
docker stop pdf2course
[ -f .watch.pid ] && kill "$(cat .watch.pid)" 2>/dev/null; rm -f .watch.pid
