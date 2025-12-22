"""
Tech Contract Reviewer - Based on David Tollen's Framework
A Flask application for AI-powered contract review using Claude API
"""

import os
import json
import tempfile
import subprocess
import zipfile
import shutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
import anthropic

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
UPLOAD_FOLDER = tempfile.mkdtemp()
ALLOWED_EXTENSIONS = {'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Initialize Anthropic client lazily to avoid startup errors
def get_anthropic_client():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
    return anthropic.Anthropic(api_key=api_key, timeout=120.0)  # 2 minute timeout

# Tollen's Key Contract Clauses (prioritized by importance)
TOLLEN_CLAUSES = [
    {
        "name": "IP Ownership & Licenses",
        "priority": 1,
        "description": "Who owns the intellectual property and what rights are granted",
        "keywords": ["intellectual property", "IP", "ownership", "license", "proprietary", 
                    "work product", "deliverables", "copyright", "patent", "trade secret",
                    "background IP", "foreground IP", "derivative works"]
    },
    {
        "name": "Limitation of Liability",
        "priority": 2,
        "description": "Caps on damages and exclusions of liability types",
        "keywords": ["limitation of liability", "liability cap", "damages", "consequential",
                    "indirect damages", "special damages", "punitive", "exclusion", "waiver",
                    "maximum liability", "aggregate liability"]
    },
    {
        "name": "Indemnification",
        "priority": 3,
        "description": "Who protects whom from third-party claims",
        "keywords": ["indemnify", "indemnification", "hold harmless", "defend", "third party claims",
                    "IP indemnity", "infringement", "indemnitor", "indemnitee"]
    },
    {
        "name": "Warranties & Disclaimers",
        "priority": 4,
        "description": "Promises about quality and functionality",
        "keywords": ["warranty", "warranties", "represents", "warrants", "disclaimer",
                    "AS IS", "merchantability", "fitness for purpose", "non-infringement",
                    "warranty period", "remedy"]
    },
    {
        "name": "Data Security & Privacy",
        "priority": 5,
        "description": "Protection of data and compliance with privacy laws",
        "keywords": ["data security", "privacy", "personal data", "confidential", "GDPR",
                    "CCPA", "data protection", "breach notification", "encryption",
                    "data processing", "PII", "sensitive data"]
    },
    {
        "name": "Termination Rights",
        "priority": 6,
        "description": "How and when the agreement can be ended",
        "keywords": ["termination", "terminate", "expiration", "renewal", "cancellation",
                    "for cause", "for convenience", "cure period", "wind-down", "survival"]
    },
    {
        "name": "Acceptance Testing",
        "priority": 7,
        "description": "Process for accepting deliverables",
        "keywords": ["acceptance", "testing", "acceptance criteria", "acceptance period",
                    "rejection", "defects", "bugs", "remediation", "milestone"]
    },
    {
        "name": "SLAs & Support",
        "priority": 8,
        "description": "Service levels and ongoing support obligations",
        "keywords": ["SLA", "service level", "uptime", "availability", "response time",
                    "support", "maintenance", "credits", "performance"]
    }
]


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def convert_doc_to_docx(doc_path):
    """Convert .doc to .docx using LibreOffice"""
    output_dir = os.path.dirname(doc_path)
    try:
        subprocess.run([
            'soffice', '--headless', '--convert-to', 'docx',
            '--outdir', output_dir, doc_path
        ], check=True, capture_output=True, timeout=60)
        docx_path = doc_path.rsplit('.', 1)[0] + '.docx'
        if os.path.exists(docx_path):
            return docx_path
    except subprocess.TimeoutExpired:
        raise Exception("Document conversion timed out")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Document conversion failed: {e.stderr.decode()}")
    raise Exception("Conversion failed - output file not created")


def extract_text_from_docx(docx_path):
    """Extract text from docx using pandoc for better formatting"""
    try:
        result = subprocess.run(
            ['pandoc', docx_path, '-t', 'plain', '--wrap=none'],
            capture_output=True, text=True, check=True, timeout=30
        )
        return result.stdout
    except Exception:
        # Fallback: manual extraction from XML
        return extract_text_manually(docx_path)


def extract_text_manually(docx_path):
    """Fallback text extraction by reading document.xml directly"""
    import xml.etree.ElementTree as ET
    
    with zipfile.ZipFile(docx_path, 'r') as z:
        xml_content = z.read('word/document.xml')
    
    root = ET.fromstring(xml_content)
    namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    
    text_parts = []
    for elem in root.iter():
        if elem.tag == '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t':
            if elem.text:
                text_parts.append(elem.text)
        elif elem.tag == '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p':
            text_parts.append('\n')
    
    return ''.join(text_parts)


def analyze_contract_with_claude(contract_text, party_type, comment_level):
    """Send contract to Claude for analysis based on Tollen's framework"""
    
    level_descriptions = {
        "friendly": """FRIENDLY review approach:
- Accept most standard terms without comment
- Only flag major risks that could cause significant harm
- Suggest minimal, non-confrontational changes
- Focus on clarifications rather than substantive changes
- Tone: collaborative and trusting""",
        
        "moderate": """MODERATE review approach:
- Flag both major and moderate risks
- Suggest balanced modifications that protect interests without being aggressive
- Recommend industry-standard protections
- Point out one-sided provisions but suggest reasonable compromises
- Tone: professional and fair""",
        
        "aggressive": """AGGRESSIVE review approach:
- Flag all potentially unfavorable provisions
- Push hard for maximum protection
- Challenge any one-sided terms
- Suggest alternative language that strongly favors the client
- Negotiate every material point
- Tone: assertive and protective"""
    }
    
    party_perspective = {
        "vendor": "You represent the VENDOR/PROVIDER (the party selling software or services). Focus on protecting the vendor's interests: limiting liability, retaining IP rights, ensuring payment, and minimizing warranty obligations.",
        "customer": "You represent the CUSTOMER/LICENSEE (the party buying software or services). Focus on protecting the customer's interests: ensuring deliverable quality, securing broad licenses, protecting data, and maintaining termination rights."
    }
    
    clauses_info = "\n".join([
        f"{c['priority']}. {c['name']}: {c['description']}"
        for c in TOLLEN_CLAUSES
    ])
    
    prompt = f"""You are an expert technology contracts attorney trained in David Tollen's approach to IT agreements (as outlined in "The Tech Contracts Handbook").

{party_perspective[party_type]}

{level_descriptions[comment_level]}

Analyze the following contract and provide a detailed review. For each issue found, include:
1. The clause category (from the priority list below)
2. The exact quote from the contract
3. The risk level (HIGH, MEDIUM, or LOW)
4. Why this is a concern from the {party_type}'s perspective
5. Specific suggested language changes

PRIORITY CLAUSE CATEGORIES (analyze in this order):
{clauses_info}

Respond in this exact JSON format:
{{
    "summary": "Brief 2-3 sentence overall assessment of the contract",
    "overall_risk": "HIGH|MEDIUM|LOW",
    "issues": [
        {{
            "clause_category": "Name from priority list",
            "priority": 1-8,
            "quote": "Exact text from contract",
            "risk_level": "HIGH|MEDIUM|LOW",
            "concern": "Why this is problematic for the {party_type}",
            "recommendation": "Specific suggested changes or alternative language",
            "tollen_principle": "Reference to relevant Tollen principle if applicable"
        }}
    ],
    "missing_clauses": [
        {{
            "clause_category": "Name of missing clause",
            "priority": 1-8,
            "importance": "Why this should be added",
            "suggested_language": "Draft language to add"
        }}
    ],
    "positive_aspects": ["List of provisions that are already favorable"]
}}

CONTRACT TEXT:
{contract_text[:20000]}"""  # Limit to ~20k chars for API

    try:
        client = get_anthropic_client()
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        return json.loads(response_text.strip())
    
    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse analysis: {str(e)}",
            "raw_response": response_text if 'response_text' in locals() else None
        }
    except ValueError as e:
        return {"error": str(e)}
    except anthropic.APITimeoutError as e:
        return {"error": "Analysis request timed out. The contract may be too large or complex. Please try a shorter document."}
    except anthropic.APIError as e:
        return {"error": f"API error: {str(e)}"}
    except Exception as e:
        app.logger.exception("Unexpected error during Anthropic analysis")
        return {"error": f"Unexpected error during analysis: {str(e)}"}


def add_comments_to_docx(docx_path, analysis, output_path):
    """Add review comments to the document"""
    import xml.etree.ElementTree as ET
    
    # Create working directory
    work_dir = tempfile.mkdtemp()
    
    try:
        # Extract docx
        with zipfile.ZipFile(docx_path, 'r') as z:
            z.extractall(work_dir)
        
        # Read document.xml
        doc_xml_path = os.path.join(work_dir, 'word', 'document.xml')
        ET.register_namespace('', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
        ET.register_namespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
        ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
        
        # Create comments.xml
        comments = []
        comment_id = 0
        
        if 'issues' in analysis:
            for issue in analysis['issues']:
                comments.append({
                    'id': comment_id,
                    'author': 'Contract Reviewer',
                    'date': datetime.now().isoformat(),
                    'text': f"[{issue.get('risk_level', 'REVIEW')}] {issue.get('clause_category', 'General')}\n\n"
                           f"CONCERN: {issue.get('concern', 'N/A')}\n\n"
                           f"RECOMMENDATION: {issue.get('recommendation', 'N/A')}"
                })
                comment_id += 1
        
        if 'missing_clauses' in analysis:
            for missing in analysis['missing_clauses']:
                comments.append({
                    'id': comment_id,
                    'author': 'Contract Reviewer',
                    'date': datetime.now().isoformat(),
                    'text': f"[MISSING CLAUSE] {missing.get('clause_category', 'General')}\n\n"
                           f"IMPORTANCE: {missing.get('importance', 'N/A')}\n\n"
                           f"SUGGESTED: {missing.get('suggested_language', 'N/A')}"
                })
                comment_id += 1
        
        # Build comments.xml
        comments_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
'''
        for c in comments:
            comments_xml += f'''  <w:comment w:id="{c['id']}" w:author="{c['author']}" w:date="{c['date']}">
    <w:p>
      <w:r>
        <w:t>{c['text'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</w:t>
      </w:r>
    </w:p>
  </w:comment>
'''
        comments_xml += '</w:comments>'
        
        # Write comments.xml
        comments_path = os.path.join(work_dir, 'word', 'comments.xml')
        with open(comments_path, 'w', encoding='utf-8') as f:
            f.write(comments_xml)
        
        # Update [Content_Types].xml to include comments
        content_types_path = os.path.join(work_dir, '[Content_Types].xml')
        with open(content_types_path, 'r', encoding='utf-8') as f:
            content_types = f.read()
        
        if 'comments.xml' not in content_types:
            content_types = content_types.replace(
                '</Types>',
                '  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>\n</Types>'
            )
            with open(content_types_path, 'w', encoding='utf-8') as f:
                f.write(content_types)
        
        # Update document.xml.rels
        rels_path = os.path.join(work_dir, 'word', '_rels', 'document.xml.rels')
        with open(rels_path, 'r', encoding='utf-8') as f:
            rels = f.read()
        
        if 'comments.xml' not in rels:
            rels = rels.replace(
                '</Relationships>',
                '  <Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>\n</Relationships>'
            )
            with open(rels_path, 'w', encoding='utf-8') as f:
                f.write(rels)
        
        # Repack docx
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(work_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, work_dir)
                    z.write(file_path, arcname)
        
        return True
    
    except Exception as e:
        # If annotation fails, just copy the original
        shutil.copy(docx_path, output_path)
        return False
    
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    # Validate file
    if 'contract' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['contract']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload .doc or .docx'}), 400
    
    # Get parameters
    party_type = request.form.get('party_type', 'customer')
    comment_level = request.form.get('comment_level', 'moderate')
    
    if party_type not in ['vendor', 'customer']:
        return jsonify({'error': 'Invalid party type'}), 400
    if comment_level not in ['friendly', 'moderate', 'aggressive']:
        return jsonify({'error': 'Invalid comment level'}), 400
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Convert .doc to .docx if needed
        if filename.lower().endswith('.doc'):
            filepath = convert_doc_to_docx(filepath)
        
        # Extract text
        contract_text = extract_text_from_docx(filepath)
        
        if not contract_text.strip():
            return jsonify({'error': 'Could not extract text from document'}), 400
        
        # Analyze with Claude
        analysis = analyze_contract_with_claude(contract_text, party_type, comment_level)
        
        if 'error' in analysis:
            return jsonify(analysis), 500
        
        # Create annotated document
        annotated_filename = f"reviewed_{filename}"
        if not annotated_filename.endswith('.docx'):
            annotated_filename = annotated_filename.rsplit('.', 1)[0] + '.docx'
        annotated_path = os.path.join(app.config['UPLOAD_FOLDER'], annotated_filename)
        
        annotation_success = add_comments_to_docx(filepath, analysis, annotated_path)
        
        # Store paths in session for download
        session['annotated_path'] = annotated_path
        session['annotated_filename'] = annotated_filename
        
        # Return analysis with download available flag
        analysis['annotated_available'] = annotation_success
        analysis['party_type'] = party_type
        analysis['comment_level'] = comment_level
        
        return jsonify(analysis)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download')
def download():
    if 'annotated_path' not in session:
        return jsonify({'error': 'No document available'}), 404
    
    path = session['annotated_path']
    filename = session.get('annotated_filename', 'reviewed_contract.docx')
    
    if not os.path.exists(path):
        return jsonify({'error': 'Document no longer available'}), 404
    
    return send_file(path, as_attachment=True, download_name=filename)


@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    
    app.logger.exception("Unhandled exception during request")
    
    if request.path.startswith('/analyze'):
        return jsonify({'error': 'An unexpected error occurred while processing your request. Please try again.'}), 500
    
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
