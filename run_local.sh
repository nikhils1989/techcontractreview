#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Check if ANTHROPIC_API_KEY is set, if not prompt for it
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY not found in .env file"
    read -p "Please enter your Anthropic API key: " ANTHROPIC_API_KEY
    export ANTHROPIC_API_KEY
    echo ""
fi

# Activate virtual environment
source venv/bin/activate

# Run build script
./build.sh

# Run the Flask application
echo ""
echo "Starting Tech Contract Reviewer..."
echo "Access the application at: http://localhost:5001"
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
