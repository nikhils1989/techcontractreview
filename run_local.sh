#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Run the Flask application
echo ""
echo "Starting Tech Contract Reviewer..."
echo "Access the application at: http://localhost:5000"
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
