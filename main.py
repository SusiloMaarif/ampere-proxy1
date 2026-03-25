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
    # Persisting next index allows fair token rotation across script runs.
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
        # If root path, show simple dashboard
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
        # Check authorization (optional, can skip for internal use)
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

        # Build headers for backend API
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

                # Stream response
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

    # Precompute stats array
    stats = [{'token': t, 'used': 0, 'failed': 0} for t in tokens]
    idx = 0

    def pick_token():
        nonlocal idx
        # Skip tokens with high failure count
        start_idx = idx
        while True:
            stat = stats[idx]
            if stat['failed'] <= 10:
                idx = (idx + 1) % len(tokens)
return stat['token']
            idx = (idx + 1) % len(tokens)
            if idx == start_idx:
                # all tokens failed? just pick next anyway
                stat = stats[idx]
                idx = (idx + 1) % len(tokens)
                return stat['token']

    server = ThreadingHTTPServer(('0.0.0.0', port), AmpereProxyHandler)
    server.base_url = base_url
    server.tokens = tokens
    server.rr_state_file = rr_state_file
    server.pick_token = pick_token
    server.stats = stats

    print(f"⚡️ Proxy starting on http://0.0.0.0:{port}")
    print(f"🎯 Target: {base_url}")
    print(f"🔢 Loaded {len(tokens)} token(s) for round-robin balancing")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down proxy")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(
        description="Ampere/OpenRouter proxy with round-robin token balancing"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="Base URL for backend API (default: https://api.ampere.sh)")
    parser.add_argument("--api-path", default=DEFAULT_API_PATH,
                        help="API path to append (default: /v1/openrouter)")
    parser.add_argument("--token",
                        default=os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "",
                        help="Single token (overrides tokens file)")
    parser.add_argument("--tokens-file",
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.txt"),
                        help="Path to tokens file (one token per line)")
    parser.add_argument("--rr-state-file",
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tokens_rr_state"),
                        help="File to persist round-robin state")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Default model for smoke test")
    parser.add_argument("--message", default="Reply exactly: pong",
                        help="Message for smoke test")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Timeout for smoke test request")
    parser.add_argument("--serve", action="store_true",
                        help="Start local proxy server")
    parser.add_argument("--port", type=int, default=8080,
                        help="Proxy server port (for --serve)")

    args = parser.parse_args()

    tokens = []
    selected_token = args.token

    if not selected_token:
        try:
            tokens = load_tokens(args.tokens_file)
        except Exception as e:
            print(f"❌ Cannot read tokens file {args.tokens_file}: {e}")
            sys.exit(2)

    if not tokens:
        print("❌ No tokens available. Set OPENROUTER_API_KEY, pass --token, or populate --tokens-file")
        sys.exit(2)

    if args.serve:
        serve_proxy(args.port, args.base_url.rstrip("/"), tokens, args.rr_state_file)
        return

    # Smoke test mode (non-server)
    selected_token = pick_round_robin_token(tokens, args.rr_state_file)

    base = args.base_url.rstrip("/") + "/" + args.api_path.strip("/")
    url = f"{base}/chat/completions"
    body = {
        "model": args.model,
        "messages": [
            {"role": "user", "content": args.message},
        ],
        "include_reasoning": False,
        "temperature": 0,
        "max_tokens": 256,
    }

    print(f"📤 POST {url}")
    status, payload, elapsed, err = request_json(
        method="POST",
        url=url,
        token=selected_token,
        body=body,
        timeout=args.timeout,
    )

    if err:
        print(f"❌ FAIL: {err} ({elapsed:.0f} ms)")
        sys.exit(1)

    print(f"✅ Status: {status} ({elapsed:.0f} ms)")
    if status is None or not (200 <= status < 300):
        print(json.dumps(payload, indent=2)[:2000])
        sys.exit(1)
print(f"📨 Response payload: {json.dumps(payload, indent=2)[:2000]}")
    text = extract_text(payload)
    print(f"🤖 AI reply: {text if text else '[no content]'}")
    sys.exit(0)


if __name__ == "__main__":
    main()
