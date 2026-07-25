#!/usr/bin/env bash
set -euo pipefail

: "${API_KEY:?Set API_KEY (see parallel/services/api/env/variables.api.env)}"
: "${TASK_ID:?Set TASK_ID to the task id returned by scripts/push.sh}"

curl -sf -H "X-API-Key: ${API_KEY}" -o video_encoded.mp4 "http://localhost:5500/v1/tasks/${TASK_ID}/download"
