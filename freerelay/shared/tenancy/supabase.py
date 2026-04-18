from supabase import Client, create_client  # type: ignore

from freerelay.config.settings import get_settings


def get_supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        msg = "Supabase configuration is missing"
        raise ValueError(msg)
    return create_client(settings.supabase_url, settings.supabase_key)

def get_supabase_admin_client() -> Client:
    settings = get_settings()
    key = settings.supabase_service_role_key or settings.supabase_key
    if not settings.supabase_url or not key:
        raise ValueError("Supabase configuration is missing")
    return create_client(settings.supabase_url, key)
