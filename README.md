# Comfy Darkroom

A local image playground for the Nano Banana models on [Comfy Router](https://docs.comfy.org). Type a prompt, fire up to four runs at once, and watch each set land as a row in a growing feed.

![Comfy Darkroom feed with the settings drawer open and two rows of four Nano Banana 2.1 generations](docs/feed.png)

- **Models:** Nano Banana 2.1 (default), Nano Banana 2, Nano Banana Pro, Nano Banana 2 Lite, Nano Banana.
- **Runs:** 1 to 4 parallel calls per prompt, each with its own seed (base seed + run index).
- **Input images:** add several by button, drag and drop, or paste. Any output can become an input with **Use as input** or **Vary**.
- **Settings:** aspect ratio, size (1K/2K/4K), PNG or JPEG, seed, thinking level, temperature, system instruction.
- **Feed:** one row per prompt, with seeds, timing and settings beside the images. Loading tiles are small WebGL shaders that the images fade in over.

![Four runs in progress, each holding its place with a WebGL loading tile until the image lands](docs/loading.png)

Everything runs on your machine. No dependencies beyond Python 3.

## Setup

1. Get a Comfy API key at <https://platform.comfy.org/profile/api-keys>. Calls are billed to that account's credits.
2. Add it to a `.env` file:
   ```sh
   cp .env.example .env
   # then edit .env: COMFY_API_KEY=your-key
   ```
   Or export `COMFY_API_KEY` in your shell instead.
3. Start the server:
   ```sh
   python3 server.py          # or: python3 server.py 9000
   ```
4. Open <http://127.0.0.1:8765>.

## How it works

`server.py` is a small standard-library server bound to `127.0.0.1`. It serves `index.html` and forwards each run to `https://api.comfy.org/v2/models/<model>`. Your key stays on the server and never reaches the browser.

Each image is saved to `outputs/` with a `.json` file holding the prompt, settings and Router stats (time, token usage, finish reason). The feed rebuilds from that folder on reload. Delete files there to clear it.

The thinking previews the model streams back are dropped. Only the final image is kept.

## Notes

- Thinking level `LOW` is not offered: Router rejects it for Nano Banana 2.1.
- Nano Banana (2.5 Flash Image) has no size option, so the size setting is ignored for it.
- `.env` and `outputs/` are gitignored.
