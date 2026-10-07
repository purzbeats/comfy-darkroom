#!/usr/bin/env python3
"""Comfy Darkroom: a local image playground for the Nano Banana models on Comfy Router.

usage: python3 server.py [port]   (default 8765, binds 127.0.0.1 only)

Set COMFY_API_KEY in the environment or in a .env file next to this script.
The key stays server-side and is never sent to the browser. Every output is saved
to ./outputs/ with a .json sidecar holding the prompt, settings and Router stats.
"""
import base64, json, os, sys, time, uuid, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "outputs")
# Nano Banana family on Router. All share the Gemini generateContent request/response shape.
MODELS = {
    "vertexai/gemini-nano-banana-2.1": "Nano Banana 2.1",
    "vertexai/gemini-3.1-flash-image": "Nano Banana 2",
    "vertexai/gemini-3-pro-image": "Nano Banana Pro",
    "vertexai/gemini-3.1-flash-lite-image": "Nano Banana 2 Lite",
    "vertexai/gemini-2.5-flash-image": "Nano Banana",
}
DEFAULT_MODEL = "vertexai/gemini-nano-banana-2.1"
ROUTER = "https://api.comfy.org/v2/models/"
os.makedirs(OUT, exist_ok=True)


def load_key():
    key = os.environ.get("COMFY_API_KEY", "").strip()
    env = os.path.join(ROOT, ".env")
    if not key and os.path.isfile(env):
        for line in open(env):
            if line.strip().startswith("COMFY_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("COMFY_API_KEY is not set. Copy .env.example to .env and add your key "
                 "(create one at https://platform.comfy.org/profile/api-keys).")
    return key


KEY = load_key()


def build_body(req):
    parts = [{"inlineData": {"mimeType": i["mime"], "data": i["data"]}} for i in req.get("images", [])]
    parts.append({"text": req["prompt"]})
    image_config = {"imageOutputOptions": {"mimeType": req.get("mimeType", "image/png")}}
    if req.get("model") != "vertexai/gemini-2.5-flash-image":  # NB1 has no imageSize
        image_config["imageSize"] = req.get("imageSize", "1K")
    if req.get("aspectRatio") and req["aspectRatio"] != "auto":
        image_config["aspectRatio"] = req["aspectRatio"]
    gen = {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": image_config}
    if req.get("temperature") is not None:
        gen["temperature"] = float(req["temperature"])
    if req.get("seed") not in (None, ""):
        gen["seed"] = int(req["seed"])
    if req.get("thinkingLevel"):
        gen["thinkingConfig"] = {"thinkingLevel": req["thinkingLevel"]}
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
    if req.get("system"):
        body["systemInstruction"] = {"parts": [{"text": req["system"]}]}
    return body


def generate(req):
    if req.get("model") not in MODELS:
        req["model"] = DEFAULT_MODEL
    body = build_body(req)
    r = urllib.request.Request(ROUTER + req["model"], data=json.dumps(body).encode(), method="POST",
                               headers={"X-API-Key": KEY, "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            data, headers, status = json.load(resp), dict(resp.headers), resp.status
    except urllib.error.HTTPError as e:
        return 502, {"error": f"Router HTTP {e.code}", "detail": e.read().decode()[:3000],
                     "seconds": round(time.time() - t0, 1)}
    except Exception as e:  # timeout, DNS, etc.
        return 502, {"error": type(e).__name__, "detail": str(e), "seconds": round(time.time() - t0, 1)}
    secs = round(time.time() - t0, 1)

    # Collect image parts. Thought parts are previews; keep them only if nothing else came back.
    finals, thoughts, texts = [], [], []
    for c in data.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if "inlineData" in p:
                blob = (p["inlineData"].get("mimeType", "image/png"), base64.b64decode(p["inlineData"]["data"]))
            elif "fileData" in p:
                with urllib.request.urlopen(p["fileData"]["fileUri"], timeout=120) as f:
                    blob = (p["fileData"].get("mimeType", "image/png"), f.read())
            else:
                if p.get("text") and not p.get("thought"):
                    texts.append(p["text"])
                continue
            (thoughts if p.get("thought") else finals).append(blob)
    images = finals or thoughts[-1:]
    stats = {"seconds": secs, "modelVersion": data.get("modelVersion"), "usage": data.get("usageMetadata"),
             "finishReason": [c.get("finishReason") for c in data.get("candidates", [])],
             "fallbackProvider": headers.get("X-Comfy-Router-Fallback-Provider"),
             "droppedParams": headers.get("X-Comfy-Router-Dropped-Params"),
             "previewsDropped": len(thoughts) if finals else 0, "http": status}
    if not images:
        return 200, {"error": "No image returned", "text": texts, "stats": stats,
                     "promptFeedback": data.get("promptFeedback")}

    settings = {k: v for k, v in req.items() if k != "images"}
    settings["inputCount"] = len(req.get("images", []))
    saved = []
    for mime, raw in images:
        stem = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        name = stem + (".jpg" if "jpeg" in mime else ".png")
        open(os.path.join(OUT, name), "wb").write(raw)
        meta = {"file": name, "created": time.time(), "settings": settings, "stats": stats, "text": texts}
        json.dump(meta, open(os.path.join(OUT, stem + ".json"), "w"), indent=1)
        saved.append(meta)
    return 200, {"items": saved, "stats": stats, "text": texts}


def gallery():
    items = []
    for f in os.listdir(OUT):
        if f.endswith(".json"):
            try:
                items.append(json.load(open(os.path.join(OUT, f))))
            except Exception:
                pass
    return sorted(items, key=lambda m: m.get("created", 0), reverse=True)


class H(BaseHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(ROOT, "index.html"), "rb").read(), "text/html; charset=utf-8")
        if path == "/api/models":
            return self._send(200, {"models": MODELS, "default": DEFAULT_MODEL})
        if path == "/api/gallery":
            return self._send(200, gallery())
        if path.startswith("/outputs/"):
            name = os.path.basename(path)
            fp = os.path.join(OUT, name)
            if os.path.isfile(fp):
                ctype = "image/jpeg" if name.endswith(".jpg") else "image/png"
                return self._send(200, open(fp, "rb").read(), ctype)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/generate":
            return self._send(404, {"error": "not found"})
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if not req.get("prompt", "").strip():
            return self._send(400, {"error": "Prompt is empty"})
        code, payload = generate(req)
        self._send(code, payload)

    def do_DELETE(self):
        if self.path.startswith("/api/outputs/"):
            stem = os.path.splitext(os.path.basename(self.path))[0]
            for ext in (".png", ".jpg", ".json"):
                fp = os.path.join(OUT, stem + ext)
                if os.path.isfile(fp):
                    os.remove(fp)
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Comfy Darkroom: http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
