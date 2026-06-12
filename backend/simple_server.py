#!/usr/bin/env python3
"""
Lightweight fallback server for the Website Auditor project.
Uses only the Python standard library so it can run without installing dependencies.
Provides two endpoints:
  GET /health -> {status: 'ok', service: 'fallback'}
  POST /audit -> simple audit JSON compatible with the frontend

This is a pragmatic fallback when installing project dependencies fails.
"""
import json
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def fetch_url_text(url: str, timeout=10):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; WebAuditorFallback/1.0)"})
    t0 = time.time()
    with urlopen(req, timeout=timeout) as r:
        content = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
        text = content.decode(enc, errors="ignore")
    elapsed = (time.time() - t0) * 1000
    return text, len(content), elapsed


def extract_basic(text: str, final_url: str):
    # title
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = m.group(1).strip() if m else None

    # meta description
    m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', text, re.I | re.S)
    meta = m.group(1).strip() if m else None

    h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
    h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", text, re.I | re.S)
    h3 = re.findall(r"<h3[^>]*>(.*?)</h3>", text, re.I | re.S)

    imgs = re.findall(r"<img[^>]+>", text, re.I | re.S)
    alt_missing = 0
    for tag in imgs:
        if not re.search(r"alt=", tag, re.I):
            alt_missing += 1

    has_viewport = bool(re.search(r'<meta\s+name=["\']viewport["\']', text, re.I))
    has_favicon = bool(re.search(r'<link[^>]+rel=["\'](?:shortcut icon|icon)["\']', text, re.I))
    has_https = final_url.startswith("https")

    return {
        "title": title,
        "meta_description": meta,
        "h1_tags": [re.sub(r'<[^>]+>', '', t).strip() for t in h1],
        "h2_tags": [re.sub(r'<[^>]+>', '', t).strip() for t in h2][:5],
        "h3_tags": [re.sub(r'<[^>]+>', '', t).strip() for t in h3][:5],
        "alt_missing_images": alt_missing,
        "total_images": len(imgs),
        "has_viewport_meta": has_viewport,
        "has_favicon": has_favicon,
        "has_https": has_https,
    }


def compute_scores_basic(seo, perf_ms, page_size_kb):
    seo_pts = 100.0
    if not seo.get("title"): seo_pts -= 20
    elif len(seo.get("title", "")) < 30: seo_pts -= 8
    if not seo.get("meta_description"): seo_pts -= 15
    elif len(seo.get("meta_description", "")) < 120: seo_pts -= 5
    if len(seo.get("h1_tags", [])) == 0: seo_pts -= 15
    seo_score = max(0, min(100, seo_pts))

    perf_pts = 100.0
    if perf_ms > 3000: perf_pts -= 30
    elif perf_ms > 1500: perf_pts -= 10
    if page_size_kb > 1500: perf_pts -= 20
    perf_score = max(0, min(100, perf_pts))

    usab_pts = 100.0
    if not seo.get("has_favicon"): usab_pts -= 5
    if not seo.get("has_viewport_meta"): usab_pts -= 25
    usab_score = max(0, min(100, usab_pts))

    overall = (seo_score * 0.4) + (perf_score * 0.4) + (usab_score * 0.2)
    grade = "A" if overall >= 90 else "B" if overall >= 75 else "C" if overall >= 60 else "D" if overall >= 45 else "F"

    return {
        "seo_score": round(seo_score,1),
        "performance_score": round(perf_score,1),
        "usability_score": round(usab_score,1),
        "overall_score": round(overall,1),
        "grade": grade
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        b = json.dumps(data).encode('utf-8')
        self.send_response(status)
        # CORS headers so the frontend can call this API from another origin
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith('/health'):
            self._send_json({"status": "ok", "service": "fallback"})
            return
        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        # Respond to CORS preflight requests
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith('/audit'):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length).decode('utf-8') if length else '{}'
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
        target = payload.get('url') or payload.get('target') or ''
        business_context = payload.get('business_context', 'general business website')

        if not target:
            self._send_json({"error": "missing url"}, status=400); return

        try:
            text, size_bytes, elapsed_ms = fetch_url_text(target)
            seo = extract_basic(text, target)
            perf_kb = round(size_bytes / 1024.0, 1)
            scores = compute_scores_basic(seo, elapsed_ms, perf_kb)

            gaps = []
            if not seo.get('title'): gaps.append('Missing page title')
            if not seo.get('meta_description'): gaps.append('Missing meta description')
            if seo.get('alt_missing_images',0) > 0: gaps.append(f"{seo['alt_missing_images']} images missing alt text")
            if not seo.get('has_viewport_meta'): gaps.append('Missing viewport meta')

            recs = [{"title":"Improve title and meta","detail":"Ensure a concise title and meta description to improve CTR.","impact":"High","effort":"Low","metric":"Organic CTR"}]

            report = {
                "url": target,
                "scraped_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "seo": {
                    "title": seo.get('title'),
                    "title_length": len(seo.get('title') or ''),
                    "meta_description": seo.get('meta_description'),
                    "meta_desc_length": len(seo.get('meta_description') or ''),
                    "h1_tags": seo.get('h1_tags', []),
                    "h2_tags": seo.get('h2_tags', []),
                    "h3_tags": seo.get('h3_tags', []),
                    "canonical_url": None,
                    "og_title": None,
                    "og_description": None,
                    "robots_meta": None,
                    "structured_data": False,
                    "internal_links": 0,
                    "external_links": 0,
                    "broken_images": 0,
                    "alt_missing_images": seo.get('alt_missing_images',0)
                },
                "performance": {
                    "load_time_ms": round(elapsed_ms,1),
                    "page_size_kb": perf_kb,
                    "total_images": seo.get('total_images',0),
                    "scripts_count": 0,
                    "stylesheets_count": 0,
                    "has_viewport_meta": seo.get('has_viewport_meta', False),
                    "has_https": seo.get('has_https', False),
                    "server_response_ms": round(elapsed_ms,1)
                },
                "usability": {
                    "has_favicon": seo.get('has_favicon', False),
                    "has_search": False,
                    "has_contact_info": False,
                    "mobile_friendly": seo.get('has_viewport_meta', False),
                    "has_cta": False,
                    "nav_links": 0,
                    "footer_present": False,
                    "form_count": 0
                },
                "scores": scores,
                "ai_recommendations": recs,
                "critical_issues": gaps,
                "quick_wins": gaps[:3],
                "raw_gaps": gaps
            }
            self._send_json(report)
        except Exception as e:
            self._send_json({"error": "fetch failed", "detail": str(e)}, status=502)


def run(port=8000):
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"Fallback server listening on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Shutting down')
        server.server_close()


if __name__ == '__main__':
    run(8000)
