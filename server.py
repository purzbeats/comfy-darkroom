#!/usr/bin/env python3
"""Comfy Darkroom: a local image playground for the Nano Banana models on Comfy Router.

usage: python3 server.py [port]   (default 8765, binds 127.0.0.1 only)

Set COMFY_API_KEY in the environment or in a .env file next to this script.
The key stays server-side and is never sent to the browser. Every output is saved
to ./outputs/ with a .json sidecar holding the prompt, settings and Router stats.
Moodboards live in ./moodboards/ (boards.json plus any uploaded images).
"""
import base64, itertools, json, os, queue, re, sys, threading, time, uuid, urllib.request, urllib.error
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
MB_DIR = os.path.join(ROOT, "moodboards")
MB_ASSETS = os.path.join(MB_DIR, "assets")
MB_FILE = os.path.join(MB_DIR, "boards.json")
MB_LOCK = threading.Lock()
# A board item is a path the page can load: a generated output or an uploaded asset.
ITEM_RE = re.compile(r"^(outputs|moodboards/assets)/[\w.-]+$")
os.makedirs(OUT, exist_ok=True)
os.makedirs(MB_ASSETS, exist_ok=True)

# Every image is a task. A fixed pool of workers makes the Router calls, so no more than MAX_ACTIVE
# are in flight however many runs, tabs or reloads ask; the rest wait in line. The page polls
# /api/tasks for progress. Finished tasks are kept a while so the page can collect them.
MAX_ACTIVE = 8
KEEP_FINISHED = 15 * 60
TASKS = {}
TASKS_LOCK = threading.Lock()
LINE = queue.Queue()
SEQ = itertools.count()  # place in line; time.time() can tie

# The page packs a moodboard into grid sheets and sends them after the user's own references.
# This note tells the model how to read them; the user never sees it.
MOODBOARD_NOTE = (
    "The last {n} reference image{s} {are} moodboard sheet{s}: grids of example images the user collected "
    "for this piece. Treat them together as art direction only. Take the colour palette, lighting, texture, "
    "materials, mood and visual style from them. Do not copy their subjects or layouts, and do not make a grid "
    "or collage. Return one single image in that style.")


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


def prompt_text(req):
    sheets = int((req.get("moodboard") or {}).get("sheets") or 0)
    if not sheets:
        return req["prompt"]
    own = len(req.get("images", [])) - sheets
    note = MOODBOARD_NOTE.format(n=sheets, s="s" if sheets > 1 else "", are="are" if sheets > 1 else "is")
    if own > 0:
        note = (f"The first {own} reference image{'s' if own > 1 else ''} {'are' if own > 1 else 'is'} the user's own "
                "reference, to use as the request describes. ") + note
    return f"{note}\n\nCreate: {req['prompt']}"


def build_body(req):
    parts = [{"inlineData": {"mimeType": i["mime"], "data": i["data"]}} for i in req.get("images", [])]
    parts.append({"text": prompt_text(req)})
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


def generate(req, task=None):
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
        return {"error": f"Router HTTP {e.code}", "detail": e.read().decode()[:3000],
                "seconds": round(time.time() - t0, 1)}
    except Exception as e:  # timeout, DNS, etc.
        return {"error": type(e).__name__, "detail": str(e), "seconds": round(time.time() - t0, 1)}
    secs = round(time.time() - t0, 1)
    if task and task["status"] == "cancelled":  # Router finished (and billed), but the user stopped it
        return {"error": "Cancelled"}

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
        return {"error": "No image returned", "text": texts, "stats": stats,
                "promptFeedback": data.get("promptFeedback")}

    settings = {k: v for k, v in req.items() if k != "images"}
    # Count only the user's own references; moodboard sheets are internal.
    settings["inputCount"] = len(req.get("images", [])) - int((req.get("moodboard") or {}).get("sheets") or 0)
    saved = []
    for mime, raw in images:
        stem = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        name = stem + (".jpg" if "jpeg" in mime else ".png")
        open(os.path.join(OUT, name), "wb").write(raw)
        meta = {"file": name, "created": time.time(), "settings": settings, "stats": stats, "text": texts}
        json.dump(meta, open(os.path.join(OUT, stem + ".json"), "w"), indent=1)
        saved.append(meta)
    return {"items": saved, "stats": stats, "text": texts}


def submit(req):
    task = {"id": uuid.uuid4().hex[:12], "status": "queued", "created": time.time(), "seq": next(SEQ), "req": req,
            "imageCount": len(req.get("images", []))}
    with TASKS_LOCK:
        TASKS[task["id"]] = task
        LINE.put(task)
        return task_view(task)


def worker():
    while True:
        task = LINE.get()
        with TASKS_LOCK:
            if task["status"] != "queued":  # cancelled while it waited
                continue
            task["status"], task["started"] = "running", time.time()
        try:
            result = generate(task["req"], task)
        except Exception as e:  # never let one bad response take a worker down
            result = {"error": type(e).__name__, "detail": str(e)}
        with TASKS_LOCK:
            task["req"].pop("images", None)
            task["finished"] = time.time()
            if task["status"] == "cancelled":
                continue
            task["status"] = "done" if result.get("items") else "error"
            task["result"] = result


def task_view(t):
    """What the page sees of a task: its settings (without the image data), progress and result."""
    v = {k: t.get(k) for k in ("id", "status", "created", "imageCount", "result")}
    v["settings"] = {k: x for k, x in t["req"].items() if k != "images"}
    v["elapsed"] = round(time.time() - t["started"], 1) if t.get("started") else 0
    if t["status"] == "queued":
        v["ahead"] = sum(1 for o in TASKS.values() if o["status"] == "queued" and o["seq"] < t["seq"])
    return v


def tasks():
    with TASKS_LOCK:
        now = time.time()
        for tid in [k for k, t in TASKS.items() if t.get("finished") and now - t["finished"] > KEEP_FINISHED]:
            del TASKS[tid]
        return [task_view(t) for t in TASKS.values()]


def cancel(tid):
    with TASKS_LOCK:
        task = TASKS.get(tid)
        if not task:
            return 404, {"error": "No such task"}
        if task["status"] in ("queued", "running"):
            if task["status"] == "queued":
                task["req"].pop("images", None)
                task["finished"] = time.time()
            task["status"] = "cancelled"
        return 200, task_view(task)


def start_workers():
    for _ in range(MAX_ACTIVE):
        threading.Thread(target=worker, daemon=True).start()


def gallery():
    items = []
    for f in os.listdir(OUT):
        if f.endswith(".json"):
            try:
                items.append(json.load(open(os.path.join(OUT, f))))
            except Exception:
                pass
    return sorted(items, key=lambda m: m.get("created", 0), reverse=True)


def mb_load():
    try:
        return json.load(open(MB_FILE))
    except Exception:
        return []


def mb_save(boards):
    tmp = MB_FILE + ".tmp"
    json.dump(boards, open(tmp, "w"), indent=1)
    os.replace(tmp, MB_FILE)


def mb_list():
    boards = mb_load()
    for b in boards:  # hide images that were deleted from disk
        b["items"] = [i for i in b["items"] if os.path.isfile(os.path.join(ROOT, i))]
    return boards


def mb_update(board_id, req):
    with MB_LOCK:
        boards = mb_load()
        board = next((b for b in boards if b["id"] == board_id), None)
        if not board:
            return 404, {"error": "No such moodboard"}
        if isinstance(req.get("name"), str) and req["name"].strip():
            board["name"] = req["name"].strip()[:80]
        for item in req.get("add", []):
            if ITEM_RE.match(item) and item not in board["items"]:
                board["items"].append(item)
        drop = set(req.get("remove", []))
        board["items"] = [i for i in board["items"] if i not in drop]
        board["updated"] = time.time()
        mb_save(boards)
        return 200, board


def mb_upload(board_id, req):
    added = []
    for img in req.get("images", [])[:200]:
        mime = img.get("mime", "")
        ext = ".jpg" if "jpeg" in mime else ".webp" if "webp" in mime else ".png"
        name = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ext
        open(os.path.join(MB_ASSETS, name), "wb").write(base64.b64decode(img["data"]))
        added.append("moodboards/assets/" + name)
    return mb_update(board_id, {"add": added})


CTYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


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
        if path == "/api/moodboards":
            return self._send(200, mb_list())
        if path == "/api/tasks":
            return self._send(200, tasks())
        if path.startswith("/outputs/") or path.startswith("/moodboards/assets/"):
            name = os.path.basename(path)
            fp = os.path.join(OUT if path.startswith("/outputs/") else MB_ASSETS, name)
            if os.path.isfile(fp):
                ctype = CTYPES.get(os.path.splitext(name)[1], "application/octet-stream")
                return self._send(200, open(fp, "rb").read(), ctype)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        m = re.match(r"^/api/moodboards/([\w-]+)(/upload)?$", self.path)
        if self.path == "/api/moodboards":
            board = {"id": uuid.uuid4().hex[:10], "name": (req.get("name") or "Untitled moodboard").strip()[:80],
                     "created": time.time(), "updated": time.time(), "items": []}
            with MB_LOCK:
                boards = mb_load()
                boards.append(board)
                mb_save(boards)
            if req.get("add"):
                return self._send(*mb_update(board["id"], {"add": req["add"]}))
            return self._send(200, board)
        if m:
            return self._send(*(mb_upload if m.group(2) else mb_update)(m.group(1), req))
        if self.path != "/api/generate":
            return self._send(404, {"error": "not found"})
        if not req.get("prompt", "").strip():
            return self._send(400, {"error": "Prompt is empty"})
        self._send(200, submit(req))

    def do_DELETE(self):
        m = re.match(r"^/api/tasks/(\w+)$", self.path)
        if m:
            return self._send(*cancel(m.group(1)))
        if self.path.startswith("/api/outputs/"):
            stem = os.path.splitext(os.path.basename(self.path))[0]
            for ext in (".png", ".jpg", ".json"):
                fp = os.path.join(OUT, stem + ext)
                if os.path.isfile(fp):
                    os.remove(fp)
            return self._send(200, {"ok": True})
        m = re.match(r"^/api/moodboards/([\w-]+)$", self.path)
        if m:
            with MB_LOCK:
                boards = mb_load()
                gone = [b for b in boards if b["id"] == m.group(1)]
                keep = [b for b in boards if b["id"] != m.group(1)]
                mb_save(keep)
                used = {i for b in keep for i in b["items"]}
                for i in (gone[0]["items"] if gone else []):  # uploaded images no other board uses
                    if i.startswith("moodboards/assets/") and i not in used:
                        try:
                            os.remove(os.path.join(ROOT, i))
                        except OSError:
                            pass
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        if "GET /api/tasks" in str(args[0] if args else ""):  # the page polls this every second
            return
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    start_workers()
    print(f"Comfy Darkroom: http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
