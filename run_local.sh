#!/bin/bash

echo "======================================"
echo "Tech Contract Reviewer - Local Setup"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    set -a
    source .env
    set +a
    echo -e "${GREEN}✓${NC} Found .env file"
fi

# Check if OPENAI_API_KEY is set, if not prompt for it
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${YELLOW}OPENAI_API_KEY not found in .env file${NC}"
    read -p "Please enter your OpenAI API key: " OPENAI_API_KEY
    export OPENAI_API_KEY
    echo ""
fi

# Check for LibreOffice
echo ""
echo "Checking system dependencies..."
if command -v soffice &> /dev/null; then
    echo -e "${GREEN}✓${NC} LibreOffice is installed"
else
    echo -e "${RED}✗${NC} LibreOffice is NOT installed"
    echo "  Install with: brew install --cask libreoffice (macOS) or sudo apt-get install libreoffice-writer (Linux)"
    MISSING_DEPS=1
fi

# Check for Pandoc
if command -v pandoc &> /dev/null; then
    echo -e "${GREEN}✓${NC} Pandoc is installed"
else
    echo -e "${RED}✗${NC} Pandoc is NOT installed"
    echo "  Install with: brew install pandoc (macOS) or sudo apt-get install pandoc (Linux)"
    MISSING_DEPS=1
fi

if [ ! -z "$MISSING_DEPS" ]; then
    echo ""
    echo -e "${YELLOW}Please install missing system dependencies before continuing.${NC}"
    exit 1
fi

# Check Python version
echo ""
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${GREEN}✓${NC} Virtual environment already exists"
fi

# Activate virtual environment and install dependencies
echo ""
echo "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo ""
echo -e "${GREEN}======================================"
echo "Setup Complete!"
echo "======================================${NC}"
echo ""
echo "Starting Tech Contract Reviewer..."
echo "Access the application at: http://localhost:5001"
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
