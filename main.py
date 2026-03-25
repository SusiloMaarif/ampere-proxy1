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
            payload = json.loads(raw) if raw else
