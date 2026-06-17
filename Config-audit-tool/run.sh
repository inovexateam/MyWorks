#!/bin/bash
cd "$(dirname "$0")"
echo "Installing dependencies (first run only)..."
pip install -r requirements.txt --quiet
echo "Starting Config Audit tool..."
python3 app.py
