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

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo "Please create a .env file in this directory with your ANTHROPIC_API_KEY"
    echo ""
    echo "Example .env file:"
    echo "ANTHROPIC_API_KEY=your-api-key-here"
    echo ""
    echo "You can copy .env.example and fill in your API key:"
    echo "  cp .env.example .env"
    echo "  nano .env  # or use your preferred editor"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found .env file"

# Check for LibreOffice
echo ""
echo "Checking system dependencies..."
if command -v soffice &> /dev/null; then
    echo -e "${GREEN}✓${NC} LibreOffice is installed"
else
    echo -e "${RED}✗${NC} LibreOffice is NOT installed"
    echo "  Install with: sudo apt-get install libreoffice-writer"
    MISSING_DEPS=1
fi

# Check for Pandoc
if command -v pandoc &> /dev/null; then
    echo -e "${GREEN}✓${NC} Pandoc is installed"
else
    echo -e "${RED}✗${NC} Pandoc is NOT installed"
    echo "  Install with: sudo apt-get install pandoc"
    MISSING_DEPS=1
fi

if [ ! -z "$MISSING_DEPS" ]; then
    echo ""
    echo -e "${YELLOW}Installing missing system dependencies...${NC}"
    sudo apt-get update
    sudo apt-get install -y libreoffice-writer pandoc
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
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo -e "${GREEN}======================================"
echo "Setup Complete!"
echo "======================================${NC}"
echo ""
echo "To start the application:"
echo "  1. Activate the virtual environment: source venv/bin/activate"
echo "  2. Run the app: python3 app.py"
echo ""
echo "The application will be available at: http://localhost:5000"
echo ""
