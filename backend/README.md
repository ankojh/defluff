# defluff backend

FastAPI service for accepting URLs from the Mac app, storing them in Postgres, and returning clean content from YouTube or article URLs.

Content behavior:

1. YouTube URLs ask `yt-dlp` for available captions.
2. Prefer English manual captions, then English automatic captions.
3. If captions are unavailable, download the audio and transcribe it with `faster-whisper`.
4. Direct PDF URLs are fetched and text is extracted page by page.
5. Other non-YouTube URLs are fetched and converted to readable article text with `trafilatura`.
6. `/api/consume` analyzes the extracted content with local Ollama, filters against local Postgres knowledge, and returns summary, novelty, research links, and highlights.

Ollama is configured through `OLLAMA_HOST` and `OLLAMA_MODEL`. The consumption agent uses your local model, defaulting to `gemma4:26B`.

## Local Development

```sh
../scripts/setup-local-db.sh
../scripts/run-backend.sh
```

The backend logs processing steps directly in that terminal: content fetching, captions, research, local knowledge lookup, and Ollama analysis.

To run the backend in the background without opening a Terminal window:

```sh
../scripts/start-backend-service.sh
```

Stop it with:

```sh
../scripts/stop-backend-service.sh
```

Manual backend setup:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Required environment variable:

```sh
DATABASE_URL=postgresql://defluff:defluff@127.0.0.1:5432/defluff
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:26B
SEARCH_PROVIDER=duckduckgo
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_ENGINE_ID=
HF_HOME=/models/huggingface
WHISPER_MODEL=small
```

Search defaults to DuckDuckGo HTML/Lite endpoints so local development stays free. Google search is optional through the official Custom Search JSON API by setting `SEARCH_PROVIDER=google`, `GOOGLE_SEARCH_API_KEY`, and `GOOGLE_SEARCH_ENGINE_ID`.

Endpoints:

- `GET /health`
- `POST /api/captions` with body `{ "url": "https://youtube.com/watch?v=..." }`
- `POST /api/content` with body `{ "url": "https://example.com/article-or.pdf" }`
- `POST /api/consume` with body `{ "url": "https://example.com/article-or.pdf" }`
