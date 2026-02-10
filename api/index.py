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

def apply_intelligence_filter(text, mode):
    # If RAW MODE is selected, return every bit of text found
    if mode == "raw_mode":
        return text.strip()
    
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
    
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 5))
        filter_mode = request.form.get('filter_mode')
        
        query = f'"{keyword}" filetype:pdf'
        progress_data = {"current": 0, "total": limit, "status": "Searching Google...", "active": True, "preview": "Connecting..."}
        
        pdf_urls = []
        try:
            for url in search(query, num_results=limit, sleep_interval=2):
                if url.lower().endswith('.pdf'):
                    pdf_urls.append(url)
                if len(pdf_urls) >= limit: break
        except:
            progress_data["preview"] = "Google rate limit hit. Wait a moment."

        progress_data["total"] = len(pdf_urls)
        final_text = ""
        results = []

        for i, pdf_url in enumerate(pdf_urls):
            progress_data["current"] = i + 1
            progress_data["status"] = f"Mining PDF {i+1}..."
            
            try:
                r = requests.get(pdf_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code == 200:
                    f = io.BytesIO(r.content)
                    reader = PdfReader(f)
                    raw_content = ""
                    for page in reader.pages:
                        raw_content += (page.extract_text() or "") + "\n"
                    
                    extracted = apply_intelligence_filter(raw_content, filter_mode)
                    
                    if extracted.strip():
                        final_text += f"--- SOURCE: {pdf_url} ---\n{extracted}\n\n"
                        results.append({'title': pdf_url.split('/')[-1][:25], 'status': 'Success', 'content': extracted})
                        progress_data["preview"] = f"Extracted data from {pdf_url.split('/')[-1][:15]}"
                    else:
                        results.append({'title': pdf_url.split('/')[-1][:25], 'status': 'Empty/Image'})
                else:
                    results.append({'title': 'Blocked', 'status': f'HTTP {r.status_code}'})
            except:
                results.append({'title': 'Error', 'status': 'Failed'})

        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, show_download=True, full_content=final_text)
    
    return render_template('index.html', results=None)
