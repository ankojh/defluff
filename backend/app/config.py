from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://defluff:defluff@127.0.0.1:5432/defluff"
    service_name: str = "defluff-backend"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:26B"
    # How long Ollama keeps the model resident after a call. The model is
    # preloaded in parallel with content fetching, so the cold start is hidden;
    # this only needs to outlast the gaps *within* a single consume (notably the
    # web-research step). "2m" keeps it loaded while you work, then frees ~17GB
    # shortly after you stop. Don't go below ~"60s" or a single consume may
    # reload the model mid-pipeline. "-1" pins it in memory forever.
    ollama_keep_alive: str = "2m"
    analysis_max_chars: int = 30000
    # Higher budget/timeout because thinking tokens share num_predict with the
    # JSON answer; too small a budget truncates the JSON and breaks parsing.
    analysis_timeout_seconds: float = 300.0
    analysis_num_predict: int = 4096
    research_num_predict: int = 2048
    discuss_num_predict: int = 2048
    search_provider: str = "duckduckgo"
    google_search_api_key: str = ""
    google_search_engine_id: str = ""
    research_timeout_seconds: float = 8.0
    research_fetch_depth: int = 2
    research_max_documents: int = 8
    research_max_chars_per_document: int = 3500
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    # YouTube increasingly serves "Sign in to confirm you're not a bot" to
    # unauthenticated clients. Point yt-dlp at a logged-in browser's cookies
    # ("chrome", "safari", "firefox", "edge", "brave", ...) or a cookies.txt
    # file to authenticate. Browser cookies take precedence; empty = disabled.
    youtube_cookies_from_browser: str = ""
    youtube_cookie_file: str = ""

    @property
    def ollama_keep_alive_value(self) -> int | str:
        """Value to send to Ollama as ``keep_alive``.

        Ollama accepts either a number of seconds (``-1`` = keep loaded forever,
        ``0`` = unload immediately) or a duration *string* with a unit like
        ``"5m"``. A bare ``"-1"``/``"0"`` must be sent as an int, because Ollama
        parses strings as Go durations and rejects ``"-1"`` ("missing unit").
        """
        try:
            return int(self.ollama_keep_alive)
        except (TypeError, ValueError):
            return self.ollama_keep_alive

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
