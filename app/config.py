from pydantic import BaseSettings


class Settings(BaseSettings):
    # Database (we’re using SQLite locally)
    DATABASE_URL: str = "sqlite:///./app.db"

    # Supabase configuration
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # Where your FastAPI app is running
    SITE_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
