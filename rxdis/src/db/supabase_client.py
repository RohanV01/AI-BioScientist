"""
Supabase client singleton.
Workers use the service role key (bypasses RLS).
The API / UI layer uses the anon key + user JWT.
"""
from __future__ import annotations
import functools
from src.config import settings


@functools.lru_cache(maxsize=1)
def get_service_client():
    """Service-role client — bypasses RLS. Use only in Celery workers."""
    from supabase import create_client
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


@functools.lru_cache(maxsize=1)
def get_anon_client():
    """Anon client — respects RLS. Use in the FastAPI / Gradio layer."""
    from supabase import create_client
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env"
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
