import json
import time
import io
import os
import requests
import re
from flask import Flask, render_template, request, Response
from pypdf import PdfReader

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Global progress state
progress_data = {"current": 0, "total": 0, "status": "Idle", "active": False}

def inject_separators(text, line_interval):
    raw_lines = text.splitlines()
    clean_lines = [line.strip() for line in raw_lines if line.strip()]
    result = []
    for i, line in enumerate(clean_lines):
        result.append(line)
        if (i + 1) % line_interval == 0 and (i + 1) < len(clean_lines):
            result.append("__SEP__")
    return "\n".join(result)

def apply_intelligence_filter(text, mode):
    if mode == "no_filter": return text
    lines = text.splitlines()
    filtered = []
    url_p = r'https?://\S+|www\.\S+'
    eml_p = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    blacklist = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com']
    
    for line in lines:
        has_url = re.search(url_p, line)
        email_m = re.search(eml_p, line)
        valid_eml = email_m and not any(d in email_m.group().lower() for d in blacklist)
        if has_url or valid_eml:
            filtered.append(line.strip())
    return "\n".join(filtered)

def get_pdf_link(identifier):
    try:
        data = requests.get(f"https://archive.org/metadata/{identifier}", timeout=5).json()
        for f in data.get('files', []):
            if f.get('name', '').lower().endswith('.pdf'):
                return f"https://archive.org/download/{identifier}/{f['name']}"
    except: return None

@app.route('/progress-stream')
def progress_stream():
    def generate():
        while True:
            yield f"data: {json.dumps(progress_data)}\n\n"
            time.sleep(0.5)
            if progress_data["status"] == "Completed": break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/', methods=['GET', 'POST'])
def index():
    global progress_data
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 10))
        line_interval = int(request.form.get('line_interval', 30))
        filter_mode = request.form.get('filter_mode')
        
        progress_data = {"current": 0, "total": limit, "status": "Connecting...", "active": True}
        
        search_url = "https://archive.org/advancedsearch.php"
        params = {'q': f'({keyword}) AND format:PDF', 'fl[]': 'identifier,title', 'rows': limit, 'output': 'json'}
        try: docs = requests.get(search_url, params=params).json().get('response', {}).get('docs', [])
        except: docs = []

        progress_data["total"] = len(docs)
        results = []
        final_text = f"--- DATA COLLECTION: {keyword.upper()} | FILTER: {filter_mode} ---\n\n"

        for i, item in enumerate(docs):
            progress_data["current"] = i + 1
            progress_data["status"] = f"Mining: {item.get('title', 'Doc')[:20]}..."
            pdf_url = get_pdf_link(item['identifier'])
            if pdf_url:
                try:
                    r = requests.get(pdf_url, timeout=10)
                    with io.BytesIO(r.content) as f:
                        reader = PdfReader(f)
                        raw = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
                    
                    filtered = apply_intelligence_filter(raw, filter_mode)
                    processed = inject_separators(filtered, line_interval)
                    
                    if processed.strip():
                        final_text += f"SOURCE: {pdf_url}\nTITLE: {item['title']}\n" + "-"*20 + f"\n{processed}\n\n" + "="*40 + "\n\n"
                        results.append({'title': item['title'], 'status': 'Success'})
                    else: results.append({'title': item['title'], 'status': 'No Match'})
                except: results.append({'title': item['title'], 'status': 'Error'})
            else: results.append({'title': item['title'], 'status': 'Missing'})

        progress_data["status"] = "Completed"
        # We pass final_text to the template so JS can handle the download
        return render_template('index.html', results=results, keyword=keyword, show_download=True, full_content=final_text)
    
    return render_template('index.html', results=None)
