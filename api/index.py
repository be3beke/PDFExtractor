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
    lines = text.splitlines()
    filtered = []
    url_p = r'(https?://[^\s]+)|(www\.[^\s]+)|([a-zA-Z0-9.-]+\.(com|net|org|io|gov|biz|me|co))'
    eml_p = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    blacklist = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
    
    for line in lines:
        has_url = re.search(url_p, line, re.IGNORECASE)
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
    start_time = time.time() # Track total execution time
    timeout_limit = 9.0      # Vercel Free limit is 10s; we stop at 9s
    
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 5))
        delay_sec = float(request.form.get('delay', 5.0))
        filter_mode = request.form.get('filter_mode')
        
        query = f'"{keyword}" filetype:pdf'
        progress_data = {"current": 0, "total": limit, "status": "Searching...", "active": True, "preview": "Pinging Google..."}
        
        pdf_urls = []
        try:
            # Short sleep to prevent instant 429
            for url in search(query, num_results=limit, sleep_interval=2):
                if url.lower().endswith('.pdf'):
                    pdf_urls.append(url)
                if len(pdf_urls) >= limit or (time.time() - start_time) > 4: # Reserve time for downloads
                    break
        except Exception as e:
            progress_data["preview"] = "Google Blocked (429). Use a slower delay."

        progress_data["total"] = len(pdf_urls)
        final_text = ""
        results = []

        for i, pdf_url in enumerate(pdf_urls):
            # Check for Vercel Timeout
            if (time.time() - start_time) > timeout_limit:
                progress_data["preview"] = "Timeout approaching! Saving partial data..."
                break

            if i > 0: time.sleep(random.uniform(1, 2)) # Shorter jitter for Vercel efficiency

            progress_data["current"] = i + 1
            progress_data["status"] = f"Extracting {i+1}..."
            
            try:
                r = requests.get(pdf_url, timeout=5, headers={'User-Agent': random.choice(USER_AGENTS)})
                if r.status_code == 200:
                    reader = PdfReader(io.BytesIO(r.content))
                    raw_content = "\n".join([(p.extract_text() or "") for p in reader.pages])
                    
                    filtered = apply_intelligence_filter(raw_content, filter_mode)
                    if filtered.strip():
                        final_text += f"{filtered}\n\n"
                        results.append({'title': pdf_url.split('/')[-1][:20], 'status': 'Success'})
                    else:
                        results.append({'title': pdf_url.split('/')[-1][:20], 'status': 'No Matches'})
                else:
                    results.append({'title': 'Blocked', 'status': f'Error {r.status_code}'})
            except:
                results.append({'title': 'Skipped', 'status': 'Timeout'})

        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, show_download=True, full_content=final_text)
    
    return render_template('index.html', results=None)
