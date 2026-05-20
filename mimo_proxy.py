#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, hashlib, argparse, logging, socket
from typing import Optional, Dict, List
from flask import Flask, request, Response
import requests as http_requests


# ============================================================
# PUT YOUR API KEY HERE
# Paste your MiMo Token Plan Key between the quotes below
# ============================================================
API_KEY = ""  # <-- Paste your Key, e.g. API_KEY = "tp-xxxxxxxxxxxx"


DEFAULT_PORT = 1999
MIMO_API_BASE = "https://token-plan-cn.xiaomimimo.com"
MIMO_CHAT_URL = f"{MIMO_API_BASE}/v1/chat/completions"
MIMO_MODELS_URL = f"{MIMO_API_BASE}/v1/models"
VLM_MODEL = "mimo-v2-omni"
MODELS_NEED_VLM = ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-flash"]
logger = logging.getLogger("mimo-proxy")


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


ReasoningCache


reasoning_cache = ReasoningCache()
runtime_config = {"port": DEFAULT_PORT, "api_key": "", "disable_vlm": False, "debug": False}


def get_api_key() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    if runtime_config.get("api_key"):
        return runtime_config["api_key"]
    if API_KEY:
        return API_KEY
    return os.environ.get("MIMO_API_KEY", "")


def fix_reasoning_content(messages: List[dict]) -> tuple:
    fixed_count = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        if not msg.get("tool_calls"):
            continue
        if msg.get("reasoning_content"):
            continue
        cached_rc = reasoning_cache.get(msg)
        if cached_rc:
            msg["reasoning_content"] = cached_rc
            fixed_count += 1
    return messages, fixed_count


def has_images(messages: List[dict]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def describe_image_with_vlm(image_url: str, api_key: str) -> str:
    vlm_msg = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_url}},
        {"type": "text", "text": "Describe this image in detail including all text, UI, charts, layout and colors."}
    ]}]
    payload = {"model": VLM_MODEL, "messages": vlm_msg, "max_tokens": 2048, "temperature": 0.3}
    hdrs = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = http_requests.post(MIMO_CHAT_URL, headers=hdrs, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[VLM failed: {e}]"


def convert_images_to_text(messages: List[dict], api_key: str) -> List[dict]:
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        new_content = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url:
                    desc = describe_image_with_vlm(url, api_key)
                    new_content.append({"type": "text", "text": f"[Image]\n{desc}"})
                else:
                    new_content.append(part)
            else:
                new_content.append(part)
        msg["content"] = new_content
    return messages


def cache_reasoning_from_response(data: dict):
    for choice in data.get("choices", []):
        msg = choice.get("message", {})
        rc = msg.get("reasoning_content")
        if rc:
            reasoning_cache.put(msg, rc)


app = Flask(__name__)


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
@app.route("/chat/completions", methods=["POST", "OPTIONS"])
def proxy_chat_completions():
    if request.method == "OPTIONS":
        r = Response(status=204)
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "*"
        return r
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=400, content_type="application/json")
    api_key = get_api_key()
    if not api_key:
        return Response(json.dumps({"error": "API Key not set. Set API_KEY in code or use --api-key or MIMO_API_KEY env"}), status=401, content_type="application/json")
    messages = payload.get("messages", [])
    model = payload.get("model", "")
    is_stream = payload.get("stream", False)
    logger.info(f"[Request] model={model}, messages={len(messages)}, stream={is_stream}")
    messages, fixed_count = fix_reasoning_content(messages)
    if fixed_count:
        payload["messages"] = messages
    if not runtime_config["disable_vlm"] and has_images(messages):
        if any(m in model.lower() for m in MODELS_NEED_VLM):
            payload["messages"] = convert_images_to_text(payload["messages"], api_key)
    fwd_headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if is_stream:
        return _handle_streaming(payload, fwd_headers)
    return _handle_non_streaming(payload, fwd_headers)


def _handle_non_streaming(payload, headers):
    try:
        resp = http_requests.post(MIMO_CHAT_URL, headers=headers, json=payload, timeout=180)
    except http_requests.exceptions.Timeout:
        return Response(json.dumps({"error": "upstream timeout"}), status=504, content_type="application/json")
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=502, content_type="application/json")
    if resp.status_code != 200:
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    try:
        data = resp.json()
    except Exception:
        return Response(resp.content, status=200, content_type="application/json")
    cache_reasoning_from_response(data)
    return Response(json.dumps(data, ensure_ascii=False), status=200, content_type="application/json; charset=utf-8")


def _handle_streaming(payload, headers):
    acc = {"reasoning_content": "", "content": "", "tool_calls": []}

    def generate():
        try:
            resp = http_requests.post(MIMO_CHAT_URL, headers=headers, json=payload, timeout=180, stream=True)
        except Exception as e:
            err = {"error": {"message": f"proxy error: {e}", "type": "proxy_error"}}
            yield "data: " + json.dumps(err, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
            return
        if resp.status_code != 200:
            err = {"error": {"message": f"upstream {resp.status_code}", "type": "api_error"}}
            yield "data: " + json.dumps(err, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
            return
        resp.encoding = "utf-8"
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                if acc["reasoning_content"]:
                    final_msg = {}
                    if acc["content"]:
                        final_msg["content"] = acc["content"]
                    if acc["tool_calls"]:
                        final_msg["tool_calls"] = acc["tool_calls"]
                    reasoning_cache.put(final_msg, acc["reasoning_content"])
                yield "data: [DONE]\n\n"
                return
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                yield line + "\n\n"
                continue
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("reasoning_content"):
                    acc["reasoning_content"] += delta["reasoning_content"]
                if delta.get("content"):
                    acc["content"] += delta["content"]
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        while len(acc["tool_calls"]) <= idx:
                            acc["tool_calls"].append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if tc.get("id"):
                            acc["tool_calls"][idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            acc["tool_calls"][idx]["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            acc["tool_calls"][idx]["function"]["arguments"] += fn["arguments"]
            yield line + "\n\n"

    return Response(generate(), status=200, content_type="text/event-stream; charset=utf-8",
                   headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.route("/v1/models", methods=["GET"])
@app.route("/models", methods=["GET"])
def proxy_models():
    api_key = get_api_key()
    if not api_key:
        return Response(json.dumps({"error": "API Key not set"}), status=401, content_type="application/json")
    try:
        resp = http_requests.get(MIMO_MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
        return Response(resp.content, status=resp.status_code, content_type="application/json")
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=502, content_type="application/json")


@app.route("/health", methods=["GET"])
def health_check():
    return Response(json.dumps({"status": "ok", "cache_size": reasoning_cache.size,
        "vlm_enabled": not runtime_config["disable_vlm"]}, ensure_ascii=False),
        status=200, content_type="application/json; charset=utf-8")


def main():
    parser = argparse.ArgumentParser(description="MiMo API Proxy")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--api-key", type=str, default="")
    parser.add_argument("--no-vlm", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    runtime_config["port"] = args.port
    runtime_config["api_key"] = args.api_key
    runtime_config["disable_vlm"] = args.no_vlm or os.environ.get("MIMO_DISABLE_VLM", "") == "1"
    runtime_config["debug"] = args.debug
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    effective_key = args.api_key or API_KEY or os.environ.get("MIMO_API_KEY", "")
    local_ip = get_local_ip()
    print()
    print("=" * 60)
    print("  MiMo API Proxy")
    print("=" * 60)
    print(f"  Listen:    http://0.0.0.0:{args.port}")
    key_status = "set" if effective_key else "NOT SET - fill API_KEY at top of file"
    print(f"  API Key:   {key_status}")
    vlm_status = "off" if runtime_config["disable_vlm"] else "on"
    print(f"  VLM:       {vlm_status}")
    print("-" * 60)
    print("  Trae config:")
    print(f"    URL:     http://{local_ip}:{args.port}/v1/chat/completions")
    print("    Model:   mimo-v2.5-pro / mimo-v2.5 / etc")
    print("-" * 60)
    print(f"  Health:    http://{local_ip}:{args.port}/health")
    print("=" * 60)
    if not effective_key:
        print("  WARNING: API Key not detected! Set via:")
        print('    1. Edit API_KEY = "" at top of this file')
        print("    2. python mimo_proxy.py --api-key tp-xxx")
        print("    3. set MIMO_API_KEY=tp-xxx")
    print()
    app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
