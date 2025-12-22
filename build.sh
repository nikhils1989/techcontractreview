#!/usr/bin/env bash
# Build script for Render deployment

set -o errexit

# Install system dependencies
apt-get update
apt-get install -y --no-install-recommends \
    libreoffice-writer \
    pandoc

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

echo "Build completed successfully!"
