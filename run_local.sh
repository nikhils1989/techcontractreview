#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Activate virtual environment
source venv/bin/activate

# Run build script
./build.sh

# Run the Flask application
echo ""
echo "Starting Tech Contract Reviewer..."
echo "Access the application at: http://localhost:5000"
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
