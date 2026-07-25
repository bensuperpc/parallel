#!/usr/bin/env bash
set -euo pipefail

: "${API_KEY:?Set API_KEY (see parallel/services/api/env/variables.api.env)}"

curl -sf -H "X-API-Key: ${API_KEY}" -F "file=@video.mp4" "http://localhost:5500/v1/upload"
