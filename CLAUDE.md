# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Comfy Darkroom: a local image playground for the Nano Banana (Gemini image) models on Comfy Router. Two source files and zero dependencies: `server.py` (Python 3 standard library only) and `index.html` (one file with inline CSS and vanilla JS, no build step, no framework). Keep it that way — don't add packages, bundlers or extra source files without a reason.

## Commands

```sh
python3 server.py          # serves http://127.0.0.1:8765 (optional port arg: python3 server.py 9000)
```

- The server exits at startup if `COMFY_API_KEY` is missing (env var, or `.env` next to `server.py`; see `.env.example`). Every `/api/generate` call is a real, billed Router request.
- There are no tests, linter or build. To check a change, run the server and use the app (or drive it with a browser).
- `index.html` is re-read from disk on every request, so front-end edits only need a page reload; `server.py` edits need a restart.
- README screenshots in `docs/` come from `scripts/screenshots.mjs` (puppeteer-core, installed with `npm i --no-save puppeteer-core`; set `CHROME` to the browser path, the default is macOS). It makes one real 4-image 1K run. The README asks for the screenshots to be retaken with any UI change.

## Architecture

**Request flow.** The browser builds a request (`requestFrom` / `generate` in `index.html`) and fires one `POST /api/generate` per image *in parallel* (seed, seed+1, …); the `ThreadingHTTPServer` forwards each to `https://api.comfy.org/v2/models/<model>`. `build_body` in `server.py` maps the request onto the Gemini `generateContent` shape. The API key stays server-side and is never sent to the browser. The README table "What the controls send" documents the UI-label → Router-field mapping; keep it in sync when controls change.

**Persistence is the filesystem, no database.** Each result is saved to `outputs/<timestamp>-<hex>.png|jpg` with a `.json` sidecar (`file`, `created`, `settings`, `stats`, `text`). `GET /api/gallery` rebuilds the feed by reading every sidecar, and the front end groups rows by `settings.jobId`. Deleting an image removes its file and sidecar. Moodboards live in `moodboards/boards.json` (written atomically through a `.tmp` + `os.replace`, guarded by `MB_LOCK`); uploaded board images go in `moodboards/assets/`. A board item is a relative path that must match `ITEM_RE` (`outputs/...` or `moodboards/assets/...`). `outputs/`, `moodboards/` and `.env` are gitignored.

**Moodboards are split between client and server.** The browser packs a board into up to 6 grid sheets of up to 6 cells (`planSheets` / `drawSheet` / `moodboardSheets`, canvas-drawn, cached) and appends them *after* the user's own reference images, sending `moodboard.sheets = N`. The server (`prompt_text`) uses that count to prefix the prompt with `MOODBOARD_NOTE`. The note is not saved, and `settings.inputCount` excludes the sheets, so the feed shows the prompt as the user typed it.

**Response handling.** Router may return thought-preview images as well as the final one. The server keeps the final images and falls back to the last thought only if nothing else came back. Router headers (`X-Comfy-Router-Fallback-Provider`, `X-Comfy-Router-Dropped-Params`) and usage go into `stats`. Router errors come back as 502 with `detail`; `friendlyError` in `index.html` turns them into plain-language messages.

**Front end structure.** Hash routing between three views (`create`, `organize`, `moodboards`; `route()` / `go()`). A single `state` object, and `render()` redraws the feed from `state.jobs`. User settings persist in `localStorage` (`darkroom-settings`, active board in `darkroom-moodboard`). Loading tiles are drawn by one shared WebGL loop.

## Model quirks to preserve

- Models are listed in `MODELS` in `server.py` and `MODEL_INFO` in `index.html`; add a new model in both.
- Nano Banana (`vertexai/gemini-2.5-flash-image`) has no `imageSize`; the server omits it and the UI disables Resolution.
- Planning level `LOW` is deliberately not offered (Router rejects it for Nano Banana 2.1).
- Shape `auto` means leave `aspectRatio` unset.

## UI copy

The interface deliberately uses plain-language labels with a short hint on each control (Shape, Creativity, Planning, Style notes…) rather than API terms. Follow that voice for new controls and error messages.
