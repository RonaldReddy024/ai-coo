# app/supabase_client.py

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

# --- Locate and load .env from the project root ---

# This file is in:  ai-coo/app/supabase_client.py
# So project root is: parent of the "app" folder
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load .env explicitly
load_dotenv(dotenv_path=ENV_PATH)

# Debug logger
logger = logging.getLogger(__name__)

# --- Read env vars ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

SUPABASE_AVAILABLE = bool(SUPABASE_URL and SUPABASE_ANON_KEY)

if not SUPABASE_AVAILABLE:
    logger.warning(
        "SUPABASE_URL or SUPABASE_ANON_KEY is not configured. "
        "Supabase-backed endpoints will be disabled."
    )
    supabase: Client | None = None
else:
    # --- Create Supabase client ---
    supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
