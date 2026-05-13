#!/bin/sh
set -eu

docker build -f docker/Dockerfile -t versarr:smoke .
docker run --rm versarr:smoke versarr config-check

