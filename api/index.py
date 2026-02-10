import json
import time
import io
import requests
import re
import random
from flask import Flask, render_template, request, Response
from pypdf import PdfReader
from googlesearch import search 

app = Flask(__name__, template_folder='../templates', static_folder='../static')

progress_data = {"current": 0, "total": 0, "status": "Idle", "active": False, "preview": ""}
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def apply_intelligence_filter(text, mode):
    if mode == "raw_mode":
        return text # No filtering, return everything
    
    lines = text.splitlines()
    filtered = []
    url_p = r'(https?://[^\s]+)|(www\.[^\s]+)|([a-zA-Z0-9.-]+\.(com|net|org|io|gov|biz|me|co|info|edu))'
    eml_p = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    for line in lines:
        line = line.strip()
        if not line: continue
        has_url = re.search(url_p, line, re.IGNORECASE)
        has_email = re.search(eml_p, line)
        
        if mode == "leads_only":
            if has_url or has_email: filtered.append(line)
        else: # urls_only
            if has_url: filtered.append(line)
                
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
    start_time = time.time()
    timeout_limit = 9.5 
    
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 5))
        filter_mode = request.form.get('filter_mode')
        
        query = f'"{keyword}" filetype:pdf'
        progress_data = {"current": 0, "total": limit, "status": "Searching...", "active": True, "preview": "Pinging Google..."}
        
        pdf_urls = []
        try:
            for url in search(query, num_results=limit, sleep_interval=2):
                if url.lower().endswith('.pdf'):
                    pdf_urls.append(url)
                if len(pdf_urls) >= limit or (time.time() - start_time) > 4: break
        except:
            progress_data["preview"] = "Google Blocked. Slow down."

        progress_data["total"] = len(pdf_urls)
        final_text = ""
        results = []

        for i, pdf_url in enumerate(pdf_urls):
            if (time.time() - start_time) > timeout_limit: break
            progress_data["current"] = i + 1
            progress_data["status"] = f"Extracting {i+1}/{len(pdf_urls)}..."
            
            try:
                r = requests.get(pdf_url, timeout=5, headers={'User-Agent': random.choice(USER_AGENTS)})
                if r.status_code == 200:
                    reader = PdfReader(io.BytesIO(r.content))
                    raw_content = ""
                    for page in reader.pages:
                        raw_content += (page.extract_text() or "") + "\n"
                    
                    extracted = apply_intelligence_filter(raw_content, filter_mode)
                    
                    if extracted.strip():
                        final_text += f"--- SOURCE: {pdf_url} ---\n{extracted}\n\n"
                        results.append({'title': pdf_url.split('/')[-1][:20], 'status': 'Success', 'content': extracted})
                    else:
                        results.append({'title': pdf_url.split('/')[-1][:20], 'status': 'Empty Result'})
                else:
                    results.append({'title': 'Error', 'status': f'HTTP {r.status_code}'})
            except:
                results.append({'title': 'Error', 'status': 'Timeout'})

        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, show_download=True, full_content=final_text)
    
    return render_template('index.html', results=None)
