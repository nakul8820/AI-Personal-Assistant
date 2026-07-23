from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/auth/callback"

    # LLM / Voice
    llm_provider: str = "groq"  # "groq" or "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    # OpenRouter — fallback when Groq is rate-limited
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini-search-preview:free"  # OpenAI GPT OSS 20B free tier
    sarvam_api_key: str = ""

    # Database
    database_url: str = ""  # If postgresql:// or postgres://, connects to PostgreSQL; otherwise SQLite at db_path
    db_path: str = "tokens.db"

    # App & Security Whitelist
    session_secret: str = "dev-insecure-change-me"
    token_encryption_key: str = ""  # Fernet key; auto-generated if blank (dev only)
    frontend_origin: str = "http://localhost:3000"
    allowed_user_emails: list[str] = []  # Optional whitelist: e.g. ["patelnakul36@gmail.com"]
    enable_debug_routes: bool = True  # set false in production
    session_max_age_hours: int = 8   # browser session cookie lifetime in hours
    idle_timeout_minutes: int = 5    # lock the assistant after N minutes of inactivity

    @property
    def google_scopes(self) -> list[str]:
        return [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/tasks",
            "https://www.googleapis.com/auth/contacts.readonly",
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
