"""Minimal Supabase client setup for the FastAPI app."""

import os

from dotenv import load_dotenv
from supabase import Client, create_client

from .config import settings

# Load .env values if you're using a .env file
load_dotenv()

SUPABASE_URL = settings.SUPABASE_URL or os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = settings.SUPABASE_ANON_KEY or os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

