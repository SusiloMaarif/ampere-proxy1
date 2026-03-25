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
                "active_tokens": active,
                "total_tokens": total,
                "total_requests": total_used,
                "total_failed": total_failed
            }
            self.wfile.write(json.dumps(info, indent=2).encode("utf-8"))
        else:
            self.handle_proxy()

    def handle_proxy(self):
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer sk-") and not self.headers.get("x-api-key", "").startswith("sk-"):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized, requires Bearer sk-..."}).encode("utf-8"))
            return

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else None

        selected_token = self.server.pick_token()
        target_url = f"{self.server.base_url}{self.path}"

        proxy_headers = {
            "Accept": self.headers.get("Accept", "application/json"),
            "Content-Type": self.headers.get("Content-Type", "application/json"),
            "User-Agent": "ampere-python-proxy/1.0",
            "Authorization": f"Bearer {selected_token}",
            "x-api-key": selected_token,
            "X-API-Key": selected_token,
        }

        req = urllib.request.Request(url=target_url, method=self.command, headers=proxy_headers, data=post_body)
        try:
            started = time.time()
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Proxy-Token-Used", selected_token[:15] + "...")
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "connection", "access-control-allow-origin"):
                        self.send_header(k, v)
                self.end_headers()

                while chunk := resp.read(8192):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Access-Control-Allow-Origin", "*")
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding", "connection", "access-control-allow-origin"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            print(f"Proxy Error: {e}")
            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


def serve_proxy(port, base_url, tokens, rr_state_file):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        pass

    stats = [{'token': t, 'used': 0, 'failed': 0} for t in tokens]
    idx = 0

    def pick_token():
        nonlocal idx
        start_idx = idx
        while True:
            stat = stats[idx]
            if stat['failed'] <= 10:
                idx = (idx + 1)
