# Tech Contract Reviewer

An AI-powered technology contract review application based on David Tollen's framework from "The Tech Contracts Handbook."

## Features

- **AI-Powered Analysis**: Uses Claude API to review contracts intelligently
- **Party-Specific Review**: Tailored feedback for Vendor or Customer perspective
- **Three Review Levels**: Friendly, Moderate, or Aggressive negotiation stance
- **Prioritized Issues**: 8 key clause categories ranked by importance
- **Dual Output**:
  - HTML report with prioritized issues
  - Annotated .docx with embedded comments
- **Multiple Formats**: Supports both .doc and .docx uploads

## Clause Priority (Tollen Framework)

1. **IP Ownership & Licenses** - Who owns the work product
2. **Limitation of Liability** - Caps on damages
3. **Indemnification** - Third-party claim protection
4. **Warranties & Disclaimers** - Quality promises
5. **Data Security & Privacy** - Data protection obligations
6. **Termination Rights** - Exit provisions
7. **Acceptance Testing** - Deliverable acceptance process
8. **SLAs & Support** - Service level commitments

## Local Development

### Prerequisites

- Python 3.9+
- LibreOffice (for .doc conversion)
- Pandoc (for text extraction)

### macOS Setup

```bash
# Install system dependencies
brew install --cask libreoffice
brew install pandoc

# Clone and setup
git clone https://github.com/nikhils1989/tech-contract-reviewer.git
cd tech-contract-reviewer

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="your-api-key-here"
export SECRET_KEY="dev-secret-key"

# Run the application
python3 app.py
```

### Ubuntu/Debian Setup

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y libreoffice-writer pandoc

# Clone and setup
git clone https://github.com/nikhils1989/tech-contract-reviewer.git
cd tech-contract-reviewer

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="your-api-key-here"
export SECRET_KEY="dev-secret-key"

# Run the application
python3 app.py
```

Visit `http://localhost:5000` in your browser.

## Deployment to Render

### Option 1: Using render.yaml (Recommended)

1. Push this repository to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click "New +" → "Blueprint"
4. Connect your GitHub repository
5. Render will detect `render.yaml` and configure automatically
6. **Important**: Add your `ANTHROPIC_API_KEY` in Environment Variables

### Option 2: Manual Setup

1. Create a new "Web Service" on Render
2. Connect your GitHub repository
3. Configure:
   - **Runtime**: Python 3
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Add Environment Variables:
   - `ANTHROPIC_API_KEY`: Your Claude API key
   - `SECRET_KEY`: A random secret string

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Yes |
| `SECRET_KEY` | Flask session secret | Yes (auto-generated on Render) |
| `PORT` | Server port | No (provided by Render) |
| `DEBUG` | Enable debug mode | No (default: false) |

## GitHub Setup

```bash
# Initialize git repository
cd tech-contract-reviewer
git init
git add .
git commit -m "Initial commit: Tech Contract Reviewer"

# Add your GitHub remote
git remote add origin https://github.com/nikhils1989/tech-contract-reviewer.git
git branch -M main
git push -u origin main
```

## API Usage

### Analyze Endpoint

```
POST /analyze
Content-Type: multipart/form-data

Parameters:
- contract: File (.doc or .docx)
- party_type: "vendor" or "customer"
- comment_level: "friendly", "moderate", or "aggressive"
```

### Download Annotated Document

```
GET /download
```

Returns the annotated .docx file with review comments.

## Project Structure

```
tech-contract-reviewer/
├── app.py              # Main Flask application
├── templates/
│   └── index.html      # Frontend template
├── requirements.txt    # Python dependencies
├── render.yaml         # Render deployment config
├── build.sh           # Build script for Render
└── README.md          # This file
```

## Limitations

- Maximum file size: 16MB
- Contract text limited to ~50,000 characters for API
- .doc conversion requires LibreOffice
- Analysis time: 30-60 seconds depending on contract length

## License

MIT License - See LICENSE file for details.

## Acknowledgments

Based on David Tollen's "The Tech Contracts Handbook" - an essential resource for technology contract drafting and negotiation.

---

*This tool provides guidance only and does not constitute legal advice. Always consult with a qualified attorney for legal matters.*
