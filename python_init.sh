#!/usr/bin/env bash
set -euo pipefail

if [ -d "myenv" ]; then
    echo "Deleting existing virtual environment 'myenv'..."
    rm -rf myenv
fi

python3 -m venv myenv
source myenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Run: 'source myenv/bin/activate' to activate the virtual environment."
