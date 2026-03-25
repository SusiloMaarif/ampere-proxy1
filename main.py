import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import traceback
import http.server
import socketserver

DEFAULT_BASE_URL = "https://api.ampere.sh"
DEFAULT_API_PATH = "/v1/openrouter"
DEFAULT_MODEL = "moonshotai/kimi-k2.5"


def load_tokens(tokens_path):
    tokens = []
    with open(tokens_path, "r", encoding="utf-8") as f:
        for line in f:
            token = line.strip()
            if token and not token.startswith("#"):
                tokens.append(token)
    return tokens


def pick_round_robin_token(tokens, state_path):
    idx = 0
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            idx = int(f.read().strip() or "0")
    except Exception:
        idx = 0

    selected = tokens[idx % len(tokens)]
    next_idx = (idx + 1) % len(tokens)

    try:
        with open(state_path, "w", encoding="utf-8") as f:
            f.write(str(next_idx))
    except Exception:
        pass

    return selected


def request_json(method, url, token, body=None, timeout=30):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ampere-python-proxy/1.0",
        "Authorization": f"Bearer {token}",
        "x-api-key": token,
        "X-API-Key": token,
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url=url, method=method, headers=headers, data=data)

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = (time.time() - started) * 1000
            payload = json.loads(raw) if raw else {}
            return resp.status, payload, elapsed, None
    except urllib.error.HTTPError as e:
        error_text = ""
        content_type = ""
        try:
            content_type = e.headers.get("Content-Type", "")
            error_text = e.read().decode("utf-8", errors="replace")
            if "application/json" in content_type.lower():
                error_payload = json.loads(error_text)
            else:
                error_payload = {
                    "error": f"HTTP {e.code}",
                    "contentType": content_type,
                    "body": error_text[:1200],
                }
        except Exception:
            error_payload = {
                "error": f"HTTP {e.code}",
                "contentType": content_type,
                "body": error_text[:1200] if error_text else "Could not parse error body",
            }
        elapsed = (time.time() - started) * 1000
        return e.code, error_payload, elapsed, None
    except Exception as e:
        elapsed = (time.time() - started) * 1000
        return None, None, elapsed, str(e)


def extract_text(payload):
    try:
        message = payload["choices"][0]["message"]
        content = message.get("content")
        if content:
            return content
        return None
    except Exception:
        return None


class AmpereProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, x-api-key, X-API-Key")
        self.end_headers()

    def do_POST(self):
        self.handle_proxy()

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
active = sum(1 for s in getattr(self.server, 'stats', []) if s['failed'] <= 10)
            total = len(getattr(self.server, 'tokens', []))
            total_used = sum(s['used'] for s in getattr(self.server, 'stats', []))
            total_failed = sum(s['failed'] for s in getattr(self.server, 'stats', []))
            info = {
                "status": "ok",
                "active_tokens": active
