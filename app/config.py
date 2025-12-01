from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Local DB (we're using SQLite by default)
    DATABASE_URL: str = "sqlite:///./app.db"

    # Supabase configuration (can be None locally)
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # Where your FastAPI app lives
    SITE_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
