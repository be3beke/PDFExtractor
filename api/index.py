import json
import time
import io
import requests
import re
import random # For human-like delays
from flask import Flask, render_template, request, Response
from pypdf import PdfReader
from googlesearch import search 

app = Flask(__name__, template_folder='../templates', static_folder='../static')

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
    lines = text.splitlines()
    filtered = []
    url_p = r'https?://\S+|www\.\S+'
    eml_p = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    blacklist = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com']
    
    for line in lines:
        has_url = re.search(url_p, line)
        valid_eml = False
        if mode == "leads_only":
            email_m = re.search(eml_p, line)
            if email_m:
                email_val = email_m.group().lower()
                if not any(domain in email_val for domain in blacklist):
                    valid_eml = True
        
        if has_url or valid_eml:
            filtered.append(line.strip())
    return "\n".join(filtered)

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
        delay_sec = float(request.form.get('delay', 2.0)) # New delay parameter
        
        query = f"{keyword} filetype:pdf"
        progress_data = {"current": 0, "total": limit, "status": "Searching Google...", "active": True}
        
        pdf_urls = []
        try:
            # Added a slight pause in search to prevent Google 429s
            for url in search(query, num_results=limit, sleep_interval=2):
                if url.lower().endswith('.pdf'):
                    pdf_urls.append(url)
        except Exception:
            pass

        progress_data["total"] = len(pdf_urls)
        results = []
        final_text = "" 
        url_pattern = r'https?://\S+|www\.\S+'

        for i, pdf_url in enumerate(pdf_urls):
            # Apply the smart delay before each download (except the first)
            if i > 0:
                actual_delay = delay_sec + random.uniform(0.5, 1.5) # Add jitter
                progress_data["status"] = f"Waiting {round(actual_delay, 1)}s to stay stealthy..."
                time.sleep(actual_delay)

            progress_data["current"] = i + 1
            progress_data["status"] = f"Extracting PDF {i+1}..."
            
            try:
                r = requests.get(pdf_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
                if r.status_code == 200:
                    with io.BytesIO(r.content) as f:
                        reader = PdfReader(f)
                        raw_content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
                    
                    if not re.search(url_pattern, raw_content):
                        results.append({'title': pdf_url.split('/')[-1][:30], 'status': 'Skipped (No URLs)'})
                        continue

                    filtered = apply_intelligence_filter(raw_content, filter_mode)
                    processed = inject_separators(filtered, line_interval)
                    
                    if processed.strip():
                        final_text += f"{processed}\n\n"
                        results.append({'title': pdf_url.split('/')[-1][:30], 'status': 'Success'})
                    else:
                        results.append({'title': pdf_url.split('/')[-1][:30], 'status': 'No Matching Lines'})
                else:
                    results.append({'title': 'Domain Blocked', 'status': f'Error {r.status_code}'})
            except Exception:
                results.append({'title': 'Host Error', 'status': 'Conn. Failed'})

        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, show_download=True, full_content=final_text)
    
    return render_template('index.html', results=None)
