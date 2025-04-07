#!/usr/bin/env bash
set -euo pipefail

curl -o video.mp4 "http://localhost:5500/download?s3_output_key=output/992ff66e-c53c-4e6c-869f-31ee9a82f8da_encoded_video.mp4&apikey=secret123"
