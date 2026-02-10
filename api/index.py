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

# Global state to track progress and terminal messages
progress_data = {"current": 0, "total": 0, "status": "Idle", "active": False, "preview": ""}

# Browser identities to prevent Google blocks
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
]

def apply_intelligence_filter(text, mode):
    """Filters lines to find URLs or professional emails."""
    lines = text.splitlines()
    filtered = []
    # Broad regex for any link or domain
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
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 5))
        delay_sec = float(request.form.get('delay', 5.0))
        filter_mode = request.form.get('filter_mode')
        
        query = f'"{keyword}" filetype:pdf'
        progress_data = {"current": 0, "total": limit, "status": "Connecting to Google...", "active": True, "preview": "Scanning web results..."}
        
        pdf_urls = []
        try:
            # Slower interval (5s) is mandatory to avoid Google 429 errors
            for url in search(query, num_results=limit, sleep_interval=5):
                if url.lower().endswith('.pdf'):
                    pdf_urls.append(url)
                if len(pdf_urls) >= limit: break
        except Exception as e:
            progress_data["status"] = "Google Blocked IP"
            progress_data["preview"] = f"Log: Google detected bot. Error: {str(e)}"

        progress_data["total"] = len(pdf_urls)
        final_text = ""
        results = []

        for i, pdf_url in enumerate(pdf_urls):
            # Stealth delay between downloads
            if i > 0:
                wait = delay_sec + random.uniform(1, 4)
                progress_data["status"] = f"Stealth Delay: {round(wait, 1)}s..."
                time.sleep(wait)

            progress_data["current"] = i + 1
            progress_data["status"] = f"Downloading PDF {i+1}..."
            
            try:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                r = requests.get(pdf_url, timeout=15, headers=headers)
                
                if r.status_code == 200:
                    with io.BytesIO(r.content) as f:
                        reader = PdfReader(f)
                        raw_content = ""
                        for page in reader.pages:
                            raw_content += (page.extract_text() or "") + "\n"
                    
                    progress_data["preview"] = f"Extracted {len(raw_content)} chars from {pdf_url.split('/')[-1][:15]}"
                    
                    filtered = apply_intelligence_filter(raw_content, filter_mode)
                    if filtered.strip():
                        final_text += f"{filtered}\n\n"
                        results.append({'title': pdf_url.split('/')[-1][:20], 'status': 'Success'})
                    else:
                        results.append({'title': pdf_url.split('/')[-1][:20], 'status': 'No Links'})
                else:
                    results.append({'title': 'Host Blocked', 'status': f'HTTP {r.status_code}'})
            except Exception as e:
                results.append({'title': 'Conn Error', 'status': 'Failed'})

        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, show_download=True, full_content=final_text)
    
    return render_template('index.html', results=None)
