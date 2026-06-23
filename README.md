<p align="center">
  <img src="macos/DefluffMac/AppBundle/Assets/DefluffIcon.png" alt="Defluff icon" width="120">
</p>

<h1 align="center">Defluff</h1>

<p align="center"><strong>Read less. Learn more.</strong></p>

<p align="center">
Paste a YouTube link, article, or PDF. Get the signal — a clean summary, chapters,
the highlights worth revisiting, and the context you were missing — without the fluff.
Runs entirely on your Mac. Nothing leaves your machine.
</p>

---

## Why Defluff

The internet is long. Most of what you open is padded — intros, tangents, SEO
filler, three paragraphs where one sentence would do. Defluff reads it for you and
hands back only what's worth your attention:

- **One TL;DR, then the depth** — a tight summary up top, with the full structure
  underneath when you want it.
- **Chapters & timestamped highlights** — for videos, jump straight to the moments
  that matter.
- **Glossary & context** — jargon explained, assumed background filled in, so you
  actually follow the argument.
- **Live research** — Defluff searches the web for the claims and concepts in the
  source and folds that context into the summary.
- **It remembers what you know** — Defluff tracks what you've already consumed and
  skips it next time, surfacing only what's *new to you*.
- **Discuss it** — ask follow-up questions about anything you just read.

Works on **YouTube videos** (captions, or auto-transcribed when there are none),
**articles**, and **PDFs**.

## Private by design

Everything runs locally — the language model (via [Ollama](https://ollama.com)),
transcription, and your reading history all live on your Mac. No accounts, no API
keys, no cloud, no telemetry. Your data is yours.

## Install

> Requires a Mac (Apple Silicon recommended) running macOS 14+.

1. **Download** the latest `Defluff.dmg` from the
   [Releases page](https://github.com/ankojh/defluff/releases/latest).
2. **Open** it and drag **Defluff** into **Applications**.
3. **Launch** Defluff. The first run sets everything up for you — it installs the
   local services and downloads the model (a one-time ~17 GB download), shown in a
   Terminal window. After that, it just works.

> **First-launch note:** the app isn't signed with a paid Apple Developer ID, so
> macOS blocks it the first time. Go to **System Settings → Privacy & Security →
> Open Anyway**, or run once:
> ```sh
> xattr -dr com.apple.quarantine /Applications/Defluff.app
> ```

Once set up, the backend, database, and model server start automatically at login
and stay running on their own — open the app whenever you like.

To remove everything: `~/Library/Application\ Support/Defluff/scripts/uninstall.sh`
(add `--purge` to also delete the model).

## How it works

Defluff is **native** — no Docker. On Apple Silicon that's the fast, low-RAM choice
(Docker can't use the Mac GPU, so the model would crawl on CPU). Three small
services run under macOS `launchd` and start themselves at login:

| Piece | What it does |
| --- | --- |
| **Ollama** | Runs the local language model that does the summarizing. |
| **FastAPI backend** | Fetches content, transcribes audio, runs research, talks to the model. |
| **Postgres** | Stores your reading history and learned knowledge. |

The macOS app is a lightweight SwiftUI client that talks to the backend on
`localhost`. Transcription uses [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper);
content extraction uses `yt-dlp`, `trafilatura`, and `pypdf`.

## For developers

```sh
# One-shot local install (installs deps, DB, model, and the login services)
./scripts/bootstrap.sh

# Build the distributable disk image
./scripts/build-dmg.sh           # -> dist/Defluff.dmg

# Build + publish a GitHub Release in one command
./scripts/release.sh             # tag from the app version, e.g. v0.1.0
```

Run the backend directly during development:

```sh
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
BACKEND_RELOAD=1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Configuration lives in `.env` (see `.env.example`). Key settings:
`OLLAMA_MODEL`, `OLLAMA_KEEP_ALIVE` (`-1` keeps the model resident for instant
answers; `0` unloads it to reclaim RAM), `DATABASE_URL`, and `SEARCH_PROVIDER`
(`duckduckgo` by default, or `google` with API credentials).

```text
backend/             FastAPI backend (app/, sql/, tests/)
macos/DefluffMac/    SwiftUI macOS client
scripts/             Install, run, build, and release scripts
```

Run the tests with `cd backend && pytest`.
