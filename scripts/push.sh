#!/usr/bin/env bash
set -euo pipefail

curl -F "file=@video.mp4" "http://localhost:5500/upload?apikey=secret123"
