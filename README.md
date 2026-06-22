<p align="center">
  <img src="macos/DefluffMac/AppBundle/Assets/DefluffIcon.png" alt="Defluff icon" width="120">
</p>

# Defluff

Skeleton for a macOS app that submits URLs to a Python backend backed by Postgres.

The app is intentionally small right now:

- macOS SwiftUI client with a URL input and submit action.
- FastAPI backend with health, URL submission, caption, and content endpoints.
- Postgres schema for storing submitted URLs and processing state.
- Local Postgres + Python 3.12 backend development.

The content flow accepts YouTube URLs, article URLs, and direct PDF URLs. YouTube URLs use `yt-dlp` to fetch captions when available; if no captions are available, the backend downloads the audio and generates timestamped captions with `faster-whisper`. Article URLs are fetched and converted into readable text with `trafilatura`. PDF URLs are fetched and text is extracted page by page. The consumption endpoint uses local Ollama with `gemma4:26B` to summarize, filter against local Postgres knowledge, and highlight important bits with timestamps when available.

## Project Layout

```text
backend/             Python FastAPI backend
  app/               Application code
  sql/               Database schema
  tests/             Backend tests
macos/DefluffMac/    SwiftUI macOS client package
scripts/             Local development scripts
```

## Backend

Prepare the local Postgres database:

```sh
./scripts/setup-local-db.sh
```

Run the backend:

```sh
./scripts/run-backend.sh
```

The backend logs processing steps directly in that terminal: content fetching, captions, Ollama research-topic planning, web research, local knowledge lookup, and Ollama analysis. The Mac app uses the streaming consume endpoint so these agent updates appear while work is still running.

Clear local consumed-memory when you do not want prior history to influence summaries:

```sh
./scripts/clear-memory.sh
```

To run the backend in the background without opening a Terminal window:

```sh
./scripts/start-backend-service.sh
```

Stop it with:

```sh
./scripts/stop-backend-service.sh
```

Or run the backend manually:

```sh
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend expects:

```sh
DATABASE_URL=postgresql://defluff:defluff@127.0.0.1:5432/defluff
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:26B
SEARCH_PROVIDER=duckduckgo
RESEARCH_FETCH_DEPTH=2
RESEARCH_MAX_DOCUMENTS=8
RESEARCH_MAX_CHARS_PER_DOCUMENT=3500
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_ENGINE_ID=
```

Search defaults to DuckDuckGo HTML/Lite endpoints so local development stays free. Google search is optional through the official Custom Search JSON API by setting `SEARCH_PROVIDER=google`, `GOOGLE_SEARCH_API_KEY`, and `GOOGLE_SEARCH_ENGINE_ID`.

Endpoints:

- `GET /health`
- `POST /api/urls` with JSON body `{ "url": "https://example.com" }`
- `POST /api/captions` with JSON body `{ "url": "https://youtube.com/watch?v=..." }`
- `POST /api/content` with JSON body `{ "url": "https://example.com/article-or.pdf" }`
- `POST /api/consume` with JSON body `{ "url": "https://example.com/article-or.pdf" }`
- `POST /api/consume/stream` with the same body, returning newline-delimited JSON progress events and a final response.

Research planning uses local Ollama with `gemma4:26B` to choose search topics from the extracted content body: main concepts, jargon, assumed context, limitations, and related topics. DuckDuckGo executes those planned topic queries. The research reader then fetches and extracts readable text from the top results, follows a small number of relevant links up to `RESEARCH_FETCH_DEPTH`, and feeds that context back into the final Ollama summary. Ollama output shown in the app is a concise reasoning summary and operational agent log, not hidden chain-of-thought.

The summary output is structured for quick consumption: TLDR, plain-English summary, flow, context helpers, term explanations, visual helpers from pulled article images when available, research context, research highlights, follow-up deep-dive questions, highlights, and key points.

## Mac App

Run the SwiftUI client:

```sh
./scripts/build-macos-app.sh
open macos/DefluffMac/.build/app/Defluff.app
```

By default it calls `http://127.0.0.1:8000`.
