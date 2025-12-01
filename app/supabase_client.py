# app/supabase_client.py

import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client

# --- Locate and load .env from the project root ---

# This file is in:  ai-coo/app/supabase_client.py
# So project root is: parent of the "app" folder
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load .env explicitly
load_dotenv(dotenv_path=ENV_PATH)

# Debug prints (you can remove these after it works)
print("DEBUG: Loading .env from:", ENV_PATH)
print("DEBUG: SUPABASE_URL from env:", repr(os.getenv("SUPABASE_URL")))

# --- Read env vars ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_URL or SUPABASE_ANON_KEY is not set. "
        "Check your .env file and path."
    )

# --- Create Supabase client ---

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
