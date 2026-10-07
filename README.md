# Comfy Darkroom

A local image playground for the Nano Banana models on [Comfy Router](https://docs.comfy.org). Describe an image, make up to four at once, and watch each set land as a row in a growing feed.

![Comfy Darkroom with the settings panel open above a row of four Nano Banana 2.1 images](docs/feed.png)

- **Models:** Nano Banana 2.1 (default), Nano Banana 2, Nano Banana Pro, Nano Banana 2 Lite and Nano Banana, each with a one-line note on when to use it.
- **Images:** make 1 to 4 per prompt. They run at the same time, each with its own seed.
- **References:** add images by button, drag and drop, or paste. They are numbered, so a prompt can say "the jacket from image 2". Any result can become a reference with **Edit**, or seed a new set with **Variations**.
- **Plain-language controls:** Shape (Square, Wide, Tall, Poster…), Resolution, and under *More controls* Creativity, Planning, Seed, File type and Style notes. Each has a short hint.
- **Feed:** one row per prompt, with its settings beside the images, plus **Run again**, **Use these settings** and **Delete**. Failed images explain what went wrong and offer **Try again**.

![Four images developing: each holds its place with a WebGL loading tile until the image fades in](docs/loading.png)

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

## What the controls send

The labels are friendlier than the API. This is what each one sets on the Router request:

| In Darkroom | Router field |
|---|---|
| Images | number of parallel requests (seed + 0, + 1, …) |
| Shape | `imageConfig.aspectRatio` (Auto leaves it unset) |
| Resolution | `imageConfig.imageSize` |
| Creativity | `temperature` (Steady 0 to Wild 2, default 1) |
| Planning: Auto, Quick, Balanced, Careful | `thinkingConfig.thinkingLevel`: unset, `MINIMAL`, `MEDIUM`, `HIGH` |
| Seed | `seed` |
| File type | `imageConfig.imageOutputOptions.mimeType` |
| Style notes | `systemInstruction` |

## Updating the screenshots

The images in `docs/` come from `scripts/screenshots.mjs`. Retake them with any UI change:

```sh
npm i --no-save puppeteer-core     # once
python3 server.py &                # needs a working key
node scripts/screenshots.mjs       # makes one 4-image run at 1K
```

Set `CHROME` if Chrome isn't at the default macOS path.

## Notes

- Planning level `LOW` is not offered: Router rejects it for Nano Banana 2.1.
- Nano Banana (2.5 Flash Image) has one resolution, so Resolution is turned off for it.
- `.env` and `outputs/` are gitignored.

![The first screen: example prompts and tips](docs/welcome.png)
