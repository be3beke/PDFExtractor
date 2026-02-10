import json
import time
import io
import os
import requests
import re
from flask import Flask, render_template, request, send_file, Response
from pypdf import PdfReader

app = Flask(__name__)

# Global progress state
progress_data = {"current": 0, "total": 0, "status": "Idle", "active": False}

def inject_separators(text, line_interval):
    """Adds __SEP__ every X non-empty lines."""
    raw_lines = text.splitlines()
    clean_lines = [line.strip() for line in raw_lines if line.strip()]
    
    result = []
    for i, line in enumerate(clean_lines):
        result.append(line)
        if (i + 1) % line_interval == 0 and (i + 1) < len(clean_lines):
            result.append("__SEP__")
    return "\n".join(result)

def apply_intelligence_filter(text, mode):
    """Filters lines for URLs or Professional Emails (Excludes generic providers)."""
    if mode == "no_filter":
        return text
    
    lines = text.splitlines()
    filtered = []
    # Regex for URLs and Emails
    url_p = r'https?://\S+|www\.\S+'
    eml_p = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    blacklist = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com']
    
    for line in lines:
        has_url = re.search(url_p, line)
        email_m = re.search(eml_p, line)
        
        # Check if email is professional (not in blacklist)
        valid_eml = False
        if email_m:
            email_val = email_m.group().lower()
            if not any(domain in email_val for domain in blacklist):
                valid_eml = True
        
        if has_url or valid_eml:
            filtered.append(line.strip())
            
    return "\n".join(filtered)

def get_pdf_link(identifier):
    """Finds the download link for the specific PDF file."""
    try:
        data = requests.get(f"https://archive.org/metadata/{identifier}", timeout=10).json()
        for f in data.get('files', []):
            if f.get('name', '').lower().endswith('.pdf'):
                return f"https://archive.org/download/{identifier}/{f['name']}"
    except:
        return None
    return None

@app.route('/progress-stream')
def progress_stream():
    """Server-Sent Events: Pushes updates to the UI."""
    def generate():
        while True:
            yield f"data: {json.dumps(progress_data)}\n\n"
            time.sleep(0.4)
            if progress_data["status"] == "Completed":
                break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/', methods=['GET', 'POST'])
def index():
    global progress_data
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 10))
        line_interval = int(request.form.get('line_interval', 30))
        filter_mode = request.form.get('filter_mode')
        
        progress_data = {"current": 0, "total": limit, "status": "Initializing...", "active": True}
        
        # Archive.org Search
        search_url = "https://archive.org/advancedsearch.php"
        params = {'q': f'({keyword}) AND format:PDF', 'fl[]': 'identifier,title', 'rows': limit, 'output': 'json'}
        
        try:
            docs = requests.get(search_url, params=params).json().get('response', {}).get('docs', [])
        except:
            docs = []

        progress_data["total"] = len(docs)
        results = []
        final_text = f"--- DATA COLLECTION: {keyword.upper()} | FILTER: {filter_mode} ---\n\n"

        for i, item in enumerate(docs):
            progress_data["current"] = i + 1
            progress_data["status"] = f"Mining: {item.get('title', 'Unknown')[:25]}..."
            
            pdf_url = get_pdf_link(item['identifier'])
            if pdf_url:
                try:
                    r = requests.get(pdf_url, timeout=25)
                    with io.BytesIO(r.content) as f:
                        reader = PdfReader(f)
                        raw_content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
                    
                    # Process intelligence
                    filtered = apply_intelligence_filter(raw_content, filter_mode)
                    processed = inject_separators(filtered, line_interval)
                    
                    if processed.strip():
                        final_text += f"SOURCE: {pdf_url}\nTITLE: {item['title']}\n" + "-"*20 + f"\n{processed}\n\n" + "="*40 + "\n\n"
                        results.append({'title': item['title'], 'status': 'Success'})
                    else:
                        results.append({'title': item['title'], 'status': 'No Matching Data'})
                except:
                    results.append({'title': item['title'], 'status': 'Extraction Error'})
            else:
                results.append({'title': item['title'], 'status': 'PDF Missing'})

        with open("all_extracted_text.txt", "w", encoding="utf-8") as f:
            f.write(final_text)
            
        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, show_download=True)
    
    return render_template('index.html')

@app.route('/download')
def download():
    return send_file("all_extracted_text.txt", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
