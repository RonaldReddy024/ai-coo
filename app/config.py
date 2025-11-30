import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Default to a local SQLite database so the app can run without an
    # external Postgres instance. Override with DATABASE_URL env var when
    # deploying to other environments.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")

settings = Settings()
