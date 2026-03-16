#!/usr/bin/env bash
# Deploy/update Noteify MPD on server. Run from /opt/mpd-workscope.
set -e
cd "$(dirname "$0")/.."
git pull
docker compose up -d --build
echo "Deploy done. Check: curl -s http://127.0.0.1:8084/health"
