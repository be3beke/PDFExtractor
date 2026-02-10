import json
import time
import io
import requests
import re
from flask import Flask, render_template, request, Response
from pypdf import PdfReader

app = Flask(__name__, template_folder='../templates')

# YOUR PROVIDED CREDENTIALS
API_KEY = "AIzaSyAcncg3oubckHwTqoNbRGUqQRnsCIRIMuM"
CX_ID = "702c976d3b8c44372"

# Global state for the progress bar
progress_data = {"current": 0, "total": 0, "status": "Idle", "preview": ""}

def apply_intelligence_filter(text, mode):
    if mode == "raw_mode":
        return text.strip()
    
    # Regex patterns for URLs and Emails
    url_p = r'(https?://[^\s]+)|(www\.[^\s]+)'
    eml_p = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    filtered = []
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        
        if mode == "leads_only" and (re.search(url_p, line) or re.search(eml_p, line)):
            filtered.append(line)
        elif mode == "urls_only" and re.search(url_p, line):
            filtered.append(line)
                
    return "\n".join(filtered)

@app.route('/progress-stream')
def progress_stream():
    def generate():
        while True:
            yield f"data: {json.dumps(progress_data)}\n\n"
            time.sleep(0.5)
            if progress_data["status"] == "Completed":
                break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/', methods=['GET', 'POST'])
def index():
    global progress_data
    start_time = time.time()
    
    if request.method == 'POST':
        keyword = request.form.get('keyword')
        limit = int(request.form.get('limit', 5))
        filter_mode = request.form.get('filter_mode')
        
        progress_data = {"current": 0, "total": limit, "status": "Connecting to Google API...", "preview": "Sending Query..."}
        
        # Google Custom Search API Call
        search_url = f"https://www.googleapis.com/customsearch/v1?key={API_KEY}&cx={CX_ID}&q={keyword}+filetype:pdf&num={limit}"
        
        results = []
        final_text = ""
        
        try:
            response = requests.get(search_url).json()
            items = response.get('items', [])
            progress_data["total"] = len(items)

            for i, item in enumerate(items):
                # Vercel 10s timeout safety check
                if (time.time() - start_time) > 9.0:
                    break
                
                pdf_url = item['link']
                progress_data["current"] = i + 1
                progress_data["status"] = f"Extracting PDF {i+1} of {len(items)}..."
                
                try:
                    r = requests.get(pdf_url, timeout=5)
                    if r.status_code == 200:
                        reader = PdfReader(io.BytesIO(r.content))
                        raw_content = "".join([(p.extract_text() or "") for p in reader.pages])
                        extracted = apply_intelligence_filter(raw_content, filter_mode)
                        
                        if extracted.strip():
                            final_text += f"--- SOURCE: {pdf_url} ---\n{extracted}\n\n"
                            results.append({'title': pdf_url.split('/')[-1][:25], 'status': 'Success', 'content': extracted})
                        else:
                            results.append({'title': pdf_url.split('/')[-1][:25], 'status': 'Empty Result'})
                except Exception:
                    results.append({'title': pdf_url.split('/')[-1][:25], 'status': 'Extraction Failed'})

        except Exception as e:
            progress_data["status"] = "API Error"
            progress_data["preview"] = str(e)

        progress_data["status"] = "Completed"
        return render_template('index.html', results=results, keyword=keyword, full_content=final_text)
    
    return render_template('index.html', results=None)

if __name__ == '__main__':
    app.run(debug=True)
