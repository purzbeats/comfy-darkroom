# Comfy Darkroom

A local image playground for the Nano Banana models on [Comfy Router](https://docs.comfy.org). Describe an image, make up to four at once, and watch each set land as a row in a growing feed.

![Comfy Darkroom with the settings panel open above a row of four Nano Banana 2.1 images](docs/feed.png)

- **Models:** Nano Banana 2.1 (default), Nano Banana 2, Nano Banana Pro, Nano Banana 2 Lite and Nano Banana, each with a one-line note on when to use it.
- **Images:** make 1 to 4 per prompt. They run at the same time, each with its own seed.
- **References:** add images by button, drag and drop, or paste. They are numbered, so a prompt can say "the jacket from image 2". Any result can become a reference with **Edit**, or seed a new set with **Variations**.
- **Plain-language controls:** Shape (Square, Wide, Tall, Poster…), Resolution, and under *More controls* Creativity, Planning, Seed, File type and Style notes. Each has a short hint.
- **Feed:** one row per prompt, with its settings beside the images, plus **Run again**, **Use these settings** and **Delete**. Failed images explain what went wrong and offer **Try again**.
- **Organize:** every image you've made in one grid. Search by prompt, select with a click (Shift-click for a range), then add the selection to a moodboard or delete it.
- **Moodboards:** collect images that share a feel, from Organize, from any result with **+ Moodboard**, or by dropping in your own. Pick a moodboard next to the prompt and new images follow its style.

![Four images developing: each holds its place with a WebGL loading tile until the image fades in](docs/loading.png)

![Organize: every generated image in one grid, five selected, with the selection bar to add them to a moodboard](docs/organize.png)

![A moodboard's page: its name, image count, and Generate with this, Add images and Delete](docs/moodboard.png)

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

### Moodboards

The app only ever shows the moodboard you picked. Behind that:

1. The page packs the board's images into grid sheets of up to 6, spread evenly over the fewest sheets (30 images make 5 sheets of 6, 25 make 5 of 5, 7 make 4 + 3). A board with more than 36 images is sampled evenly down to 36, so at most 6 sheets go out.
2. The sheets are drawn on a canvas in the browser (512px cells, cover-cropped) and cached until the board changes.
3. They are sent after any references you added yourself. The server puts a short note in front of your prompt telling the model to read the sheets as art direction (palette, lighting, texture, mood), not to copy their subjects, and to return one image rather than a grid.

The note is not saved with the image, so a row shows your prompt as you wrote it. Boards are stored in `moodboards/boards.json`; images you upload to a board go in `moodboards/assets/`.

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

The images in `docs/` come from `scripts/screenshots.mjs`. Retake them with any UI change. The moodboard shot uses your first board with images, or a demo board built from recent images that is never saved.

```sh
npm i --no-save puppeteer-core     # once
python3 server.py &                # needs a working key
node scripts/screenshots.mjs       # makes one 4-image run at 1K
```

Set `CHROME` if Chrome isn't at the default macOS path.

## Notes

- Planning level `LOW` is not offered: Router rejects it for Nano Banana 2.1.
- Nano Banana (2.5 Flash Image) has one resolution, so Resolution is turned off for it.
- `.env`, `outputs/` and `moodboards/` are gitignored.

![The first screen: example prompts and tips](docs/welcome.png)
