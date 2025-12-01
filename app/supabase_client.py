# app/supabase_client.py

import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_URL or SUPABASE_ANON_KEY is not set. "
        "Set them as environment variables before running the app."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
