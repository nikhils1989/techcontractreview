"""
Tech Contract Reviewer - Based on David Tollen's Framework
A Flask application for AI-powered contract review using ChatGPT API
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
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
UPLOAD_FOLDER = tempfile.mkdtemp()
ALLOWED_EXTENSIONS = {'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Initialize OpenAI client lazily to avoid startup errors
def get_openai_client():
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    # Set timeout to 90 seconds to prevent hanging requests
    # Reduced from 120 to ensure we fail before gunicorn worker timeout
    return OpenAI(api_key=api_key, timeout=90.0)

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


def analyze_contract_with_ai(contract_text, party_type, comment_level):
    """Send contract to ChatGPT for analysis based on David Tollen's framework"""
    
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
- Recommend industry-standard protections for technology companies
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
{contract_text[:15000]}"""  # Limit to ~15k chars for faster API response

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",  # Faster and more efficient than gpt-4-turbo-preview
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        # Validate response structure before accessing
        if not response.choices or len(response.choices) == 0:
            return {"error": "Invalid API response: no choices returned"}
        if not response.choices[0].message or not response.choices[0].message.content:
            return {"error": "Invalid API response: no content in message"}

        response_text = response.choices[0].message.content
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            parts = response_text.split("```json")
            if len(parts) > 1:
                # Get content after ```json and find closing ```
                after_json = parts[1]
                end_pos = after_json.find("```")
                response_text = after_json[:end_pos] if end_pos != -1 else after_json
        elif "```" in response_text:
            parts = response_text.split("```")
            if len(parts) >= 3:
                # Content is between first and second ```
                response_text = parts[1]
            elif len(parts) == 2:
                # Only one closing backtick, take content after
                response_text = parts[1]
        
        return json.loads(response_text.strip())
    
    except json.JSONDecodeError as e:
        app.logger.error(f"JSON decode error: {e}")
        return {
            "error": f"Failed to parse analysis: {str(e)}",
            "raw_response": response_text if 'response_text' in locals() else None
        }
    except ValueError as e:
        app.logger.error(f"Value error: {e}")
        return {"error": str(e)}
    except Exception as e:
        # Handle OpenAI API errors with detailed logging
        error_message = str(e)
        error_type = type(e).__name__
        app.logger.error(f"Error during AI analysis - Type: {error_type}, Message: {error_message}")

        if "timeout" in error_message.lower() or "timed out" in error_message.lower():
            app.logger.warning("API request timed out - consider reducing contract size or upgrading infrastructure")
            return {"error": "The AI analysis request timed out. This usually happens with very large contracts. Please try uploading a smaller document or contact support."}
        elif "connection" in error_message.lower() or "network" in error_message.lower():
            app.logger.warning(f"Network error: {error_message}")
            return {"error": f"Network error connecting to AI service. Please check your connection and try again. Error: {str(e)}"}
        elif "rate_limit" in error_message.lower():
            app.logger.warning("Rate limit exceeded")
            return {"error": "API rate limit exceeded. Please wait a moment and try again."}
        elif "api" in error_message.lower() or "openai" in error_message.lower():
            app.logger.warning(f"OpenAI API error: {error_message}")
            return {"error": f"AI service error: {str(e)}"}
        else:
            app.logger.exception("Unexpected error during AI analysis")
            return {"error": f"Unexpected error during analysis: {str(e)}"}


def extract_paragraphs_from_docx(doc_xml_path):
    """Extract paragraphs with their text content from document.xml"""
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(doc_xml_path)
        root = tree.getroot()

        # Define namespaces
        ns = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        }

        paragraphs = []
        para_elements = root.findall('.//w:p', ns)

        for idx, para in enumerate(para_elements):
            # Extract all text from the paragraph
            text_elements = para.findall('.//w:t', ns)
            para_text = ''.join([t.text or '' for t in text_elements])

            if para_text.strip():  # Only include non-empty paragraphs
                paragraphs.append({
                    'index': idx,
                    'text': para_text.strip(),
                    'element': para
                })

        return paragraphs
    except Exception as e:
        print(f"Error extracting paragraphs: {e}")
        return []


def match_issues_to_paragraphs(paragraphs, analysis):
    """Use ChatGPT to match issues to specific paragraphs"""
    if not paragraphs:
        return {}

    try:
        client = get_openai_client()

        # Prepare paragraph text for matching
        para_text = "\n\n".join([f"[Paragraph {p['index']}]: {p['text'][:200]}..." if len(p['text']) > 200 else f"[Paragraph {p['index']}]: {p['text']}" for p in paragraphs[:50]])  # Limit to first 50 paragraphs to avoid token limits

        # Prepare issues list
        issues_text = ""
        all_items = []

        if 'issues' in analysis:
            for i, issue in enumerate(analysis['issues']):
                issues_text += f"\n\nIssue {i}: {issue.get('clause_category', 'General')} - {issue.get('concern', 'N/A')}"
                all_items.append(('issue', i, issue))

        if 'missing_clauses' in analysis:
            for i, missing in enumerate(analysis['missing_clauses']):
                issues_text += f"\n\nMissing {i}: {missing.get('clause_category', 'General')} - {missing.get('importance', 'N/A')}"
                all_items.append(('missing', i, missing))

        # Ask ChatGPT to match
        prompt = f"""You are analyzing a contract document. Below are the paragraphs from the document and issues identified during review.

PARAGRAPHS:
{para_text}

ISSUES TO MATCH:
{issues_text}

For each issue or missing clause, identify which paragraph number it most closely relates to. If an issue relates to a missing clause (something that should be in the contract but isn't), return -1 for that issue.

Respond with ONLY a JSON object mapping each issue/missing to a paragraph index. Format:
{{
  "Issue 0": paragraph_index,
  "Issue 1": paragraph_index,
  "Missing 0": -1,
  ...
}}

Use -1 for missing clauses or when no good match is found."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )

        # Validate response structure before accessing
        if not response.choices or len(response.choices) == 0:
            raise ValueError("Invalid API response: no choices returned")
        if not response.choices[0].message or not response.choices[0].message.content:
            raise ValueError("Invalid API response: no content in message")

        result_text = response.choices[0].message.content.strip()

        # Parse the JSON response
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            parts = result_text.split('```')
            if len(parts) > 1:
                result_text = parts[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()

        matches = json.loads(result_text)

        # Convert to our internal format
        issue_matches = {}
        for item_type, item_idx, item_data in all_items:
            key = f"{item_type.capitalize()} {item_idx}"
            if key in matches:
                para_idx = matches[key]
                if para_idx >= 0 and para_idx < len(paragraphs):
                    issue_matches[(item_type, item_idx)] = para_idx

        return issue_matches

    except Exception as e:
        print(f"Error matching issues to paragraphs: {e}")
        return {}


def add_comments_to_docx(docx_path, analysis, output_path):
    """Add review comments to the document with proper anchoring"""
    import xml.etree.ElementTree as ET

    # Create working directory
    work_dir = tempfile.mkdtemp()

    try:
        # Extract docx
        with zipfile.ZipFile(docx_path, 'r') as z:
            z.extractall(work_dir)

        # Read document.xml
        doc_xml_path = os.path.join(work_dir, 'word', 'document.xml')

        # Register namespaces
        ns = {
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        }
        ET.register_namespace('w', ns['w'])
        ET.register_namespace('r', ns['r'])

        # Parse document
        tree = ET.parse(doc_xml_path)
        root = tree.getroot()

        # Extract paragraphs
        paragraphs = extract_paragraphs_from_docx(doc_xml_path)

        # Match issues to paragraphs
        issue_matches = match_issues_to_paragraphs(paragraphs, analysis)

        # Create comments data
        comments = []
        comment_id = 0
        comment_insertions = []  # (paragraph_index, comment_id, comment_data)

        if 'issues' in analysis:
            for i, issue in enumerate(analysis['issues']):
                comment_data = {
                    'id': comment_id,
                    'author': 'Contract Reviewer',
                    'date': datetime.now().isoformat(),
                    'text': f"[{issue.get('risk_level', 'REVIEW')}] {issue.get('clause_category', 'General')}\n\n"
                           f"CONCERN: {issue.get('concern', 'N/A')}\n\n"
                           f"RECOMMENDATION: {issue.get('recommendation', 'N/A')}"
                }
                comments.append(comment_data)

                # Find paragraph to attach comment to
                para_idx = issue_matches.get(('issue', i), 0)  # Default to first paragraph
                comment_insertions.append((para_idx, comment_id, comment_data))
                comment_id += 1

        if 'missing_clauses' in analysis:
            for i, missing in enumerate(analysis['missing_clauses']):
                comment_data = {
                    'id': comment_id,
                    'author': 'Contract Reviewer',
                    'date': datetime.now().isoformat(),
                    'text': f"[MISSING CLAUSE] {missing.get('clause_category', 'General')}\n\n"
                           f"IMPORTANCE: {missing.get('importance', 'N/A')}\n\n"
                           f"SUGGESTED: {missing.get('suggested_language', 'N/A')}"
                }
                comments.append(comment_data)

                # Missing clauses go at the end
                para_idx = len(paragraphs) - 1 if paragraphs else 0
                comment_insertions.append((para_idx, comment_id, comment_data))
                comment_id += 1

        # Insert comment markers into document.xml
        para_elements = root.findall('.//w:p', ns)

        for para_idx, comm_id, comm_data in comment_insertions:
            if para_idx < len(para_elements):
                para = para_elements[para_idx]

                # Create comment range start
                range_start = ET.Element(f"{{{ns['w']}}}commentRangeStart")
                range_start.set(f"{{{ns['w']}}}id", str(comm_id))

                # Create comment range end
                range_end = ET.Element(f"{{{ns['w']}}}commentRangeEnd")
                range_end.set(f"{{{ns['w']}}}id", str(comm_id))

                # Create comment reference run
                comment_run = ET.Element(f"{{{ns['w']}}}r")
                comment_ref = ET.SubElement(comment_run, f"{{{ns['w']}}}commentReference")
                comment_ref.set(f"{{{ns['w']}}}id", str(comm_id))

                # Insert markers: start at beginning, end and reference at end
                para.insert(0, range_start)
                para.append(range_end)
                para.append(comment_run)

        # Save modified document.xml
        tree.write(doc_xml_path, encoding='utf-8', xml_declaration=True)

        # Build comments.xml
        comments_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
'''
        for c in comments:
            escaped_text = c['text'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            comments_xml += f'''  <w:comment w:id="{c['id']}" w:author="{c['author']}" w:date="{c['date']}">
    <w:p>
      <w:r>
        <w:t xml:space="preserve">{escaped_text}</w:t>
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
            # Find the highest existing rId
            import re
            rids = re.findall(r'Id="rId(\d+)"', rels)
            max_rid = max([int(r) for r in rids]) if rids else 0
            new_rid = f"rId{max_rid + 1}"

            rels = rels.replace(
                '</Relationships>',
                f'  <Relationship Id="{new_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>\n</Relationships>'
            )
            with open(rels_path, 'w', encoding='utf-8') as f:
                f.write(rels)

        # Repack docx
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for root_dir, dirs, files in os.walk(work_dir):
                for file in files:
                    file_path = os.path.join(root_dir, file)
                    arcname = os.path.relpath(file_path, work_dir)
                    z.write(file_path, arcname)

        return True

    except Exception as e:
        print(f"Error adding comments: {e}")
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
        
        # Analyze with AI
        analysis = analyze_contract_with_ai(contract_text, party_type, comment_level)
        
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
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
